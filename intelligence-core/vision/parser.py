"""
Vision Parser for SSIP
Extracts transaction data from PDF statements, receipts, and images
using Ollama's vision models (LLaVA, Llama 3.2 Vision).
"""

import os
import re
import json
import base64
import asyncio
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, AsyncGenerator
from datetime import datetime, date
from enum import Enum

import httpx

# Optional: PDF to image conversion
try:
    import pdf2image
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from PIL import Image
    PIL_SUPPORT = True
except ImportError:
    PIL_SUPPORT = False


# =============================================================================
# Configuration
# =============================================================================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
VISION_MODEL = os.getenv("VISION_MODEL", "llava:13b")  # or llama3.2-vision:11b


class DocumentType(Enum):
    """Type of document being parsed."""
    RECEIPT = "receipt"
    BANK_STATEMENT = "bank_statement"
    CREDIT_CARD_STATEMENT = "credit_card_statement"
    INVOICE = "invoice"
    UNKNOWN = "unknown"


@dataclass
class ExtractedTransaction:
    """A single transaction extracted from a document."""
    date: Optional[str] = None
    description: str = ""
    amount: float = 0.0
    currency: str = "USD"
    category: Optional[str] = None
    merchant: Optional[str] = None
    mcc_code: Optional[str] = None  # Merchant Category Code
    transaction_type: str = "withdrawal"  # withdrawal, deposit, transfer
    confidence: float = 0.0  # 0.0 to 1.0
    raw_text: Optional[str] = None  # Original text that was parsed
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseResult:
    """Result of parsing a document."""
    document_type: DocumentType
    transactions: list[ExtractedTransaction] = field(default_factory=list)
    account_number: Optional[str] = None
    statement_period: Optional[str] = None
    total_amount: Optional[float] = None
    merchant_name: Optional[str] = None  # For receipts
    raw_response: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: int = 0
    
    def to_dict(self) -> dict:
        result = {
            "document_type": self.document_type.value,
            "transactions": [t.to_dict() for t in self.transactions],
            "account_number": self.account_number,
            "statement_period": self.statement_period,
            "total_amount": self.total_amount,
            "merchant_name": self.merchant_name,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
        }
        return result


# =============================================================================
# Prompts for Vision Model
# =============================================================================

RECEIPT_PROMPT = """Analyze this receipt image and extract all transaction information.

Return a JSON object with the following structure:
{
  "merchant_name": "Store name",
  "date": "YYYY-MM-DD",
  "items": [
    {"description": "Item name", "amount": 0.00, "quantity": 1}
  ],
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "payment_method": "cash/credit/debit",
  "currency": "USD"
}

Only return valid JSON, no other text."""

STATEMENT_PROMPT = """Analyze this bank/credit card statement image and extract all transactions.

Return a JSON object with the following structure:
{
  "account_type": "checking/savings/credit",
  "account_number_last4": "1234",
  "statement_period": "MM/DD/YYYY - MM/DD/YYYY",
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "Transaction description",
      "amount": -0.00,
      "balance": 0.00
    }
  ],
  "opening_balance": 0.00,
  "closing_balance": 0.00,
  "total_credits": 0.00,
  "total_debits": 0.00
}

Negative amounts are debits/withdrawals. Positive amounts are credits/deposits.
Only return valid JSON, no other text."""

GENERIC_PROMPT = """Analyze this financial document image and extract all relevant information.

Identify:
1. Document type (receipt, statement, invoice, etc.)
2. Date(s)
3. Amounts
4. Merchant/payee names
5. Any transaction details

Return a JSON object with your findings. Be thorough but only include information you can clearly read from the image."""


# =============================================================================
# Vision Parser Class
# =============================================================================

class VisionParser:
    """
    Parses financial documents using Ollama vision models.
    Supports receipts, bank statements, credit card statements.
    """
    
    def __init__(
        self,
        ollama_host: str = OLLAMA_HOST,
        model: str = VISION_MODEL,
        timeout: float = 120.0,
    ):
        self.ollama_host = ollama_host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=5),
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    def _image_to_base64(self, image_data: bytes) -> str:
        """Convert image bytes to base64 string."""
        return base64.b64encode(image_data).decode("utf-8")
    
    def _pdf_to_images(self, pdf_data: bytes, dpi: int = 200) -> list[bytes]:
        """Convert PDF to list of PNG images."""
        if not PDF_SUPPORT:
            raise RuntimeError(
                "PDF support not available. Install pdf2image: pip install pdf2image"
            )
        
        images = pdf2image.convert_from_bytes(pdf_data, dpi=dpi)
        result = []
        for img in images:
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            result.append(buffer.getvalue())
        return result
    
    def _detect_document_type(self, text: str) -> DocumentType:
        """Detect document type from extracted text."""
        text_lower = text.lower()
        
        if any(kw in text_lower for kw in ["statement", "account summary", "opening balance", "closing balance"]):
            if any(kw in text_lower for kw in ["credit card", "card ending", "minimum payment"]):
                return DocumentType.CREDIT_CARD_STATEMENT
            return DocumentType.BANK_STATEMENT
        
        if any(kw in text_lower for kw in ["receipt", "thank you", "subtotal", "tax", "total"]):
            return DocumentType.RECEIPT
        
        if any(kw in text_lower for kw in ["invoice", "bill to", "due date", "payment terms"]):
            return DocumentType.INVOICE
        
        return DocumentType.UNKNOWN
    
    async def _call_vision_model(
        self,
        image_base64: str,
        prompt: str,
    ) -> str:
        """Call Ollama vision model with image."""
        client = await self._get_client()
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for structured output
                "num_predict": 4096,
            },
        }
        
        response = await client.post(
            f"{self.ollama_host}/api/generate",
            json=payload,
        )
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "")
    
    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from model response."""
        # Try to find JSON in the response
        # Sometimes models wrap JSON in markdown code blocks
        json_patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
            r"\{[\s\S]*\}",
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if match.lastindex else match.group(0)
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
        
        # Try parsing the entire response as JSON
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return None
    
    def _parse_receipt_json(self, data: dict) -> ParseResult:
        """Parse receipt JSON into ParseResult."""
        transactions = []
        
        # Parse individual items
        items = data.get("items", [])
        for item in items:
            tx = ExtractedTransaction(
                date=data.get("date"),
                description=item.get("description", "Unknown item"),
                amount=float(item.get("amount", 0)),
                currency=data.get("currency", "USD"),
                merchant=data.get("merchant_name"),
                transaction_type="withdrawal",
                confidence=0.8,
            )
            transactions.append(tx)
        
        # If no items but has total, create single transaction
        if not transactions and data.get("total"):
            tx = ExtractedTransaction(
                date=data.get("date"),
                description=f"Purchase at {data.get('merchant_name', 'Unknown')}",
                amount=float(data.get("total", 0)),
                currency=data.get("currency", "USD"),
                merchant=data.get("merchant_name"),
                transaction_type="withdrawal",
                confidence=0.9,
            )
            transactions.append(tx)
        
        return ParseResult(
            document_type=DocumentType.RECEIPT,
            transactions=transactions,
            merchant_name=data.get("merchant_name"),
            total_amount=data.get("total"),
        )
    
    def _parse_statement_json(self, data: dict) -> ParseResult:
        """Parse statement JSON into ParseResult."""
        transactions = []
        
        for tx_data in data.get("transactions", []):
            amount = float(tx_data.get("amount", 0))
            tx = ExtractedTransaction(
                date=tx_data.get("date"),
                description=tx_data.get("description", ""),
                amount=abs(amount),
                currency="USD",
                transaction_type="withdrawal" if amount < 0 else "deposit",
                confidence=0.85,
            )
            transactions.append(tx)
        
        # Determine document type
        account_type = data.get("account_type", "").lower()
        if "credit" in account_type:
            doc_type = DocumentType.CREDIT_CARD_STATEMENT
        else:
            doc_type = DocumentType.BANK_STATEMENT
        
        return ParseResult(
            document_type=doc_type,
            transactions=transactions,
            account_number=data.get("account_number_last4"),
            statement_period=data.get("statement_period"),
            total_amount=data.get("closing_balance"),
        )
    
    async def parse_image(
        self,
        image_data: bytes,
        document_hint: Optional[DocumentType] = None,
    ) -> ParseResult:
        """
        Parse a single image and extract transactions.
        
        Args:
            image_data: Raw image bytes (PNG, JPEG, etc.)
            document_hint: Optional hint about document type
            
        Returns:
            ParseResult with extracted transactions
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            image_b64 = self._image_to_base64(image_data)
            
            # Select prompt based on hint
            if document_hint == DocumentType.RECEIPT:
                prompt = RECEIPT_PROMPT
            elif document_hint in (DocumentType.BANK_STATEMENT, DocumentType.CREDIT_CARD_STATEMENT):
                prompt = STATEMENT_PROMPT
            else:
                prompt = GENERIC_PROMPT
            
            # Call vision model
            response_text = await self._call_vision_model(image_b64, prompt)
            
            # Parse JSON from response
            data = self._extract_json(response_text)
            
            if data is None:
                return ParseResult(
                    document_type=DocumentType.UNKNOWN,
                    error="Failed to parse JSON from model response",
                    raw_response=response_text,
                    processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                )
            
            # Detect document type from response
            doc_type = document_hint or self._detect_document_type(response_text)
            
            # Parse based on detected type
            if doc_type == DocumentType.RECEIPT:
                result = self._parse_receipt_json(data)
            elif doc_type in (DocumentType.BANK_STATEMENT, DocumentType.CREDIT_CARD_STATEMENT):
                result = self._parse_statement_json(data)
            else:
                # Generic parsing
                result = ParseResult(
                    document_type=doc_type,
                    raw_response=response_text,
                )
            
            result.raw_response = response_text
            result.processing_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            return result
            
        except httpx.HTTPError as e:
            return ParseResult(
                document_type=DocumentType.UNKNOWN,
                error=f"HTTP error calling vision model: {e}",
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )
        except Exception as e:
            return ParseResult(
                document_type=DocumentType.UNKNOWN,
                error=f"Error parsing document: {e}",
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )
    
    async def parse_pdf(
        self,
        pdf_data: bytes,
        document_hint: Optional[DocumentType] = None,
        max_pages: int = 10,
    ) -> ParseResult:
        """
        Parse a PDF document and extract transactions from all pages.
        
        Args:
            pdf_data: Raw PDF bytes
            document_hint: Optional hint about document type
            max_pages: Maximum pages to process
            
        Returns:
            Combined ParseResult from all pages
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Convert PDF to images
            images = self._pdf_to_images(pdf_data)[:max_pages]
            
            all_transactions = []
            doc_type = document_hint or DocumentType.UNKNOWN
            account_number = None
            statement_period = None
            merchant_name = None
            
            # Process each page
            for i, img_data in enumerate(images):
                page_result = await self.parse_image(img_data, document_hint=doc_type)
                
                if page_result.error:
                    continue
                
                all_transactions.extend(page_result.transactions)
                
                # Update metadata from first valid page
                if page_result.document_type != DocumentType.UNKNOWN:
                    doc_type = page_result.document_type
                if page_result.account_number and not account_number:
                    account_number = page_result.account_number
                if page_result.statement_period and not statement_period:
                    statement_period = page_result.statement_period
                if page_result.merchant_name and not merchant_name:
                    merchant_name = page_result.merchant_name
            
            return ParseResult(
                document_type=doc_type,
                transactions=all_transactions,
                account_number=account_number,
                statement_period=statement_period,
                merchant_name=merchant_name,
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )
            
        except Exception as e:
            return ParseResult(
                document_type=DocumentType.UNKNOWN,
                error=f"Error parsing PDF: {e}",
                processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )
    
    async def parse_file(
        self,
        file_path: str | Path,
        document_hint: Optional[DocumentType] = None,
    ) -> ParseResult:
        """
        Parse a file (image or PDF) and extract transactions.
        
        Args:
            file_path: Path to file
            document_hint: Optional hint about document type
            
        Returns:
            ParseResult with extracted transactions
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return ParseResult(
                document_type=DocumentType.UNKNOWN,
                error=f"File not found: {file_path}",
            )
        
        data = file_path.read_bytes()
        
        if file_path.suffix.lower() == ".pdf":
            return await self.parse_pdf(data, document_hint)
        else:
            return await self.parse_image(data, document_hint)


# =============================================================================
# MCC (Merchant Category Code) Enrichment
# =============================================================================

# Common MCC codes and their categories
MCC_CATEGORIES = {
    # Groceries
    "5411": ("Grocery Stores", "groceries"),
    "5422": ("Freezer and Locker Meat Provisioners", "groceries"),
    "5441": ("Candy, Nut, and Confectionery Stores", "groceries"),
    "5451": ("Dairy Products Stores", "groceries"),
    "5462": ("Bakeries", "groceries"),
    
    # Restaurants
    "5812": ("Eating Places and Restaurants", "dining"),
    "5813": ("Drinking Places (Bars, Taverns)", "dining"),
    "5814": ("Fast Food Restaurants", "dining"),
    
    # Gas Stations
    "5541": ("Service Stations", "gas"),
    "5542": ("Automated Fuel Dispensers", "gas"),
    
    # Travel
    "3000-3299": ("Airlines", "travel"),
    "3500-3999": ("Hotels/Motels", "travel"),
    "4111": ("Transportation – Suburban and Local Commuter", "travel"),
    "4112": ("Passenger Railways", "travel"),
    "4121": ("Taxicabs and Limousines", "travel"),
    "4131": ("Bus Lines", "travel"),
    
    # Entertainment
    "7832": ("Motion Picture Theaters", "entertainment"),
    "7841": ("Video Tape Rental Stores", "entertainment"),
    "7911": ("Dance Halls, Studios, Schools", "entertainment"),
    "7922": ("Theatrical Producers", "entertainment"),
    "7929": ("Bands, Orchestras", "entertainment"),
    "7932": ("Billiard and Pool Establishments", "entertainment"),
    "7933": ("Bowling Alleys", "entertainment"),
    "7941": ("Athletic Fields, Commercial Sports", "entertainment"),
    
    # Utilities
    "4812": ("Telecommunication Equipment", "utilities"),
    "4814": ("Telecommunication Services", "utilities"),
    "4816": ("Computer Network Services", "utilities"),
    "4899": ("Cable and Other Pay Television", "utilities"),
    "4900": ("Utilities – Electric, Gas, Water", "utilities"),
    
    # Shopping
    "5200": ("Home Supply Warehouse Stores", "shopping"),
    "5211": ("Building Materials, Hardware Stores", "shopping"),
    "5251": ("Hardware Stores", "shopping"),
    "5261": ("Lawn and Garden Supply Stores", "shopping"),
    "5300": ("Wholesale Clubs", "shopping"),
    "5310": ("Discount Stores", "shopping"),
    "5311": ("Department Stores", "shopping"),
    "5331": ("Variety Stores", "shopping"),
    "5399": ("Miscellaneous General Merchandise", "shopping"),
    
    # Online
    "5732": ("Electronics Stores", "electronics"),
    "5733": ("Music Stores", "entertainment"),
    "5734": ("Computer Software Stores", "electronics"),
    "5735": ("Record Stores", "entertainment"),
    "5815": ("Digital Goods Media", "digital"),
    "5816": ("Digital Goods Games", "digital"),
    "5817": ("Digital Goods Applications", "digital"),
    "5818": ("Digital Goods Large Volume", "digital"),
    
    # Health
    "5912": ("Drug Stores and Pharmacies", "health"),
    "8011": ("Doctors", "health"),
    "8021": ("Dentists", "health"),
    "8031": ("Osteopaths", "health"),
    "8041": ("Chiropractors", "health"),
    "8042": ("Optometrists", "health"),
    "8043": ("Opticians", "health"),
    "8049": ("Podiatrists", "health"),
    "8050": ("Nursing and Personal Care Facilities", "health"),
    "8062": ("Hospitals", "health"),
    "8071": ("Medical and Dental Labs", "health"),
    "8099": ("Medical Services", "health"),
}


def get_mcc_category(mcc_code: str) -> tuple[str, str]:
    """
    Get category name and type from MCC code.
    
    Returns:
        Tuple of (category_name, category_type)
    """
    if mcc_code in MCC_CATEGORIES:
        return MCC_CATEGORIES[mcc_code]
    
    # Check ranges (e.g., airlines 3000-3299)
    try:
        code_int = int(mcc_code)
        if 3000 <= code_int <= 3299:
            return ("Airlines", "travel")
        if 3500 <= code_int <= 3999:
            return ("Hotels/Motels", "travel")
    except ValueError:
        pass
    
    return ("Unknown", "other")


async def enrich_with_mcc(
    transaction: ExtractedTransaction,
    ollama_host: str = OLLAMA_HOST,
) -> ExtractedTransaction:
    """
    Enrich a transaction with MCC code using LLM inference.
    
    Uses the merchant name and description to predict MCC category.
    """
    if transaction.mcc_code:
        # Already has MCC
        category_name, category_type = get_mcc_category(transaction.mcc_code)
        transaction.category = category_type
        return transaction
    
    # Use LLM to predict category from description
    prompt = f"""Given this transaction, predict the most likely merchant category.

Transaction:
- Merchant: {transaction.merchant or 'Unknown'}
- Description: {transaction.description}
- Amount: ${transaction.amount:.2f}

Return ONLY one of these categories (single word):
groceries, dining, gas, travel, entertainment, utilities, shopping, electronics, digital, health, other

Category:"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{ollama_host}/api/generate",
                json={
                    "model": "llama3.1:8b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 20},
                },
            )
            response.raise_for_status()
            result = response.json()
            category = result.get("response", "other").strip().lower()
            
            # Validate category
            valid_categories = ["groceries", "dining", "gas", "travel", "entertainment", 
                              "utilities", "shopping", "electronics", "digital", "health", "other"]
            if category in valid_categories:
                transaction.category = category
            else:
                transaction.category = "other"
                
        except Exception:
            transaction.category = "other"
    
    return transaction


# =============================================================================
# Convenience Functions
# =============================================================================

async def parse_receipt(image_path: str | Path) -> ParseResult:
    """Quick helper to parse a receipt image."""
    async with VisionParser() as parser:
        return await parser.parse_file(image_path, DocumentType.RECEIPT)


async def parse_statement(file_path: str | Path) -> ParseResult:
    """Quick helper to parse a bank/credit card statement."""
    async with VisionParser() as parser:
        return await parser.parse_file(file_path, DocumentType.BANK_STATEMENT)


async def extract_transactions(file_path: str | Path) -> list[ExtractedTransaction]:
    """Quick helper to extract transactions from any document."""
    async with VisionParser() as parser:
        result = await parser.parse_file(file_path)
        return result.transactions


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python parser.py <image_or_pdf_path>")
            sys.exit(1)
        
        file_path = sys.argv[1]
        print(f"Parsing: {file_path}")
        
        async with VisionParser() as parser:
            result = await parser.parse_file(file_path)
        
        print(f"\nDocument Type: {result.document_type.value}")
        print(f"Processing Time: {result.processing_time_ms}ms")
        
        if result.error:
            print(f"Error: {result.error}")
        else:
            print(f"\nFound {len(result.transactions)} transactions:")
            for tx in result.transactions:
                print(f"  {tx.date}: {tx.description} - ${tx.amount:.2f} ({tx.transaction_type})")
            
            if result.merchant_name:
                print(f"\nMerchant: {result.merchant_name}")
            if result.total_amount:
                print(f"Total: ${result.total_amount:.2f}")
    
    asyncio.run(main())
