"""
SSIP - Sovereign Smart Intelligence Platform
Firefly III API Wrapper

A Pythonic wrapper for Firefly III REST API with async support.
Handles authentication, transactions, accounts, and categories.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from dataclasses import dataclass
from enum import Enum

import httpx


# =============================================================================
# Configuration
# =============================================================================

FIREFLY_BASE_URL = os.getenv("FIREFLY_API_URL", "http://firefly-iii:8080")
FIREFLY_API_TOKEN = os.getenv("FIREFLY_API_TOKEN", "")


# =============================================================================
# Enums & Data Models
# =============================================================================

class TransactionType(str, Enum):
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"
    RECONCILIATION = "reconciliation"
    OPENING_BALANCE = "opening balance"


class AccountType(str, Enum):
    ASSET = "asset"
    EXPENSE = "expense"
    REVENUE = "revenue"
    LIABILITY = "liabilities"
    CASH = "cash"


@dataclass
class Account:
    """Represents a Firefly III account."""
    id: int
    name: str
    type: AccountType
    currency_code: str
    current_balance: float
    active: bool = True
    iban: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Transaction:
    """Represents a Firefly III transaction."""
    id: int
    type: TransactionType
    date: date
    amount: float
    description: str
    source_name: str
    destination_name: str
    category_name: Optional[str] = None
    budget_name: Optional[str] = None
    tags: List[str] = None
    notes: Optional[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class Category:
    """Represents a Firefly III category."""
    id: int
    name: str
    notes: Optional[str] = None


# =============================================================================
# Firefly III Client
# =============================================================================

class FireflyClient:
    """Async client for Firefly III API."""
    
    def __init__(
        self,
        base_url: str = FIREFLY_BASE_URL,
        api_token: str = FIREFLY_API_TOKEN
    ):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/api/v1",
                headers=self.headers,
                timeout=30.0
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # =========================================================================
    # Health & Info
    # =========================================================================
    
    async def get_about(self) -> Dict[str, Any]:
        """Get Firefly III system info."""
        client = await self._get_client()
        response = await client.get("/about")
        response.raise_for_status()
        return response.json().get("data", {})
    
    async def get_user(self) -> Dict[str, Any]:
        """Get current user info."""
        client = await self._get_client()
        response = await client.get("/about/user")
        response.raise_for_status()
        return response.json().get("data", {})
    
    # =========================================================================
    # Accounts
    # =========================================================================
    
    async def list_accounts(
        self,
        account_type: Optional[AccountType] = None,
        page: int = 1
    ) -> List[Account]:
        """List all accounts, optionally filtered by type."""
        client = await self._get_client()
        params = {"page": page}
        if account_type:
            params["type"] = account_type.value
        
        response = await client.get("/accounts", params=params)
        response.raise_for_status()
        
        accounts = []
        for item in response.json().get("data", []):
            attrs = item.get("attributes", {})
            accounts.append(Account(
                id=int(item["id"]),
                name=attrs.get("name", ""),
                type=AccountType(attrs.get("type", "asset")),
                currency_code=attrs.get("currency_code", "USD"),
                current_balance=float(attrs.get("current_balance", 0)),
                active=attrs.get("active", True),
                iban=attrs.get("iban"),
                notes=attrs.get("notes")
            ))
        return accounts
    
    async def get_account(self, account_id: int) -> Account:
        """Get a specific account by ID."""
        client = await self._get_client()
        response = await client.get(f"/accounts/{account_id}")
        response.raise_for_status()
        
        item = response.json().get("data", {})
        attrs = item.get("attributes", {})
        return Account(
            id=int(item["id"]),
            name=attrs.get("name", ""),
            type=AccountType(attrs.get("type", "asset")),
            currency_code=attrs.get("currency_code", "USD"),
            current_balance=float(attrs.get("current_balance", 0)),
            active=attrs.get("active", True),
            iban=attrs.get("iban"),
            notes=attrs.get("notes")
        )
    
    async def create_account(
        self,
        name: str,
        account_type: AccountType,
        currency_code: str = "USD",
        opening_balance: float = 0.0,
        iban: Optional[str] = None
    ) -> Account:
        """Create a new account."""
        client = await self._get_client()
        
        payload = {
            "name": name,
            "type": account_type.value,
            "currency_code": currency_code,
            "opening_balance": str(opening_balance),
            "active": True
        }
        if iban:
            payload["iban"] = iban
        
        response = await client.post("/accounts", json=payload)
        response.raise_for_status()
        
        item = response.json().get("data", {})
        attrs = item.get("attributes", {})
        return Account(
            id=int(item["id"]),
            name=attrs.get("name", ""),
            type=AccountType(attrs.get("type", "asset")),
            currency_code=attrs.get("currency_code", "USD"),
            current_balance=float(attrs.get("current_balance", 0)),
            active=attrs.get("active", True),
            iban=attrs.get("iban"),
            notes=attrs.get("notes")
        )
    
    # =========================================================================
    # Transactions
    # =========================================================================
    
    async def list_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        transaction_type: Optional[TransactionType] = None,
        page: int = 1
    ) -> List[Transaction]:
        """List transactions with optional filters."""
        client = await self._get_client()
        params = {"page": page}
        
        if start_date:
            params["start"] = start_date.isoformat()
        if end_date:
            params["end"] = end_date.isoformat()
        if transaction_type:
            params["type"] = transaction_type.value
        
        response = await client.get("/transactions", params=params)
        response.raise_for_status()
        
        transactions = []
        for item in response.json().get("data", []):
            attrs = item.get("attributes", {})
            # Firefly returns transactions grouped, get first split
            splits = attrs.get("transactions", [{}])
            if not splits:
                continue
            split = splits[0]
            
            transactions.append(Transaction(
                id=int(item["id"]),
                type=TransactionType(split.get("type", "withdrawal")),
                date=date.fromisoformat(split.get("date", "2000-01-01")[:10]),
                amount=float(split.get("amount", 0)),
                description=split.get("description", ""),
                source_name=split.get("source_name", ""),
                destination_name=split.get("destination_name", ""),
                category_name=split.get("category_name"),
                budget_name=split.get("budget_name"),
                tags=split.get("tags", []),
                notes=split.get("notes")
            ))
        return transactions
    
    async def get_transaction(self, transaction_id: int) -> Transaction:
        """Get a specific transaction by ID."""
        client = await self._get_client()
        response = await client.get(f"/transactions/{transaction_id}")
        response.raise_for_status()
        
        item = response.json().get("data", {})
        attrs = item.get("attributes", {})
        splits = attrs.get("transactions", [{}])
        split = splits[0] if splits else {}
        
        return Transaction(
            id=int(item["id"]),
            type=TransactionType(split.get("type", "withdrawal")),
            date=date.fromisoformat(split.get("date", "2000-01-01")[:10]),
            amount=float(split.get("amount", 0)),
            description=split.get("description", ""),
            source_name=split.get("source_name", ""),
            destination_name=split.get("destination_name", ""),
            category_name=split.get("category_name"),
            budget_name=split.get("budget_name"),
            tags=split.get("tags", []),
            notes=split.get("notes")
        )
    
    async def create_transaction(
        self,
        transaction_type: TransactionType,
        amount: float,
        description: str,
        source_account: str,
        destination_account: str,
        transaction_date: Optional[date] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> Transaction:
        """Create a new transaction."""
        client = await self._get_client()
        
        if transaction_date is None:
            transaction_date = date.today()
        
        transaction_data = {
            "type": transaction_type.value,
            "date": transaction_date.isoformat(),
            "amount": str(amount),
            "description": description,
            "source_name": source_account,
            "destination_name": destination_account
        }
        
        if category:
            transaction_data["category_name"] = category
        if tags:
            transaction_data["tags"] = tags
        if notes:
            transaction_data["notes"] = notes
        
        payload = {
            "error_if_duplicate_hash": False,
            "apply_rules": True,
            "transactions": [transaction_data]
        }
        
        response = await client.post("/transactions", json=payload)
        response.raise_for_status()
        
        item = response.json().get("data", {})
        attrs = item.get("attributes", {})
        splits = attrs.get("transactions", [{}])
        split = splits[0] if splits else {}
        
        return Transaction(
            id=int(item["id"]),
            type=TransactionType(split.get("type", transaction_type.value)),
            date=date.fromisoformat(split.get("date", transaction_date.isoformat())[:10]),
            amount=float(split.get("amount", amount)),
            description=split.get("description", description),
            source_name=split.get("source_name", source_account),
            destination_name=split.get("destination_name", destination_account),
            category_name=split.get("category_name"),
            budget_name=split.get("budget_name"),
            tags=split.get("tags", []),
            notes=split.get("notes")
        )
    
    async def delete_transaction(self, transaction_id: int) -> bool:
        """Delete a transaction by ID."""
        client = await self._get_client()
        response = await client.delete(f"/transactions/{transaction_id}")
        return response.status_code == 204
    
    # =========================================================================
    # Categories
    # =========================================================================
    
    async def list_categories(self, page: int = 1) -> List[Category]:
        """List all categories."""
        client = await self._get_client()
        response = await client.get("/categories", params={"page": page})
        response.raise_for_status()
        
        categories = []
        for item in response.json().get("data", []):
            attrs = item.get("attributes", {})
            categories.append(Category(
                id=int(item["id"]),
                name=attrs.get("name", ""),
                notes=attrs.get("notes")
            ))
        return categories
    
    async def create_category(
        self,
        name: str,
        notes: Optional[str] = None
    ) -> Category:
        """Create a new category."""
        client = await self._get_client()
        
        payload = {"name": name}
        if notes:
            payload["notes"] = notes
        
        response = await client.post("/categories", json=payload)
        response.raise_for_status()
        
        item = response.json().get("data", {})
        attrs = item.get("attributes", {})
        return Category(
            id=int(item["id"]),
            name=attrs.get("name", name),
            notes=attrs.get("notes")
        )
    
    # =========================================================================
    # Search & Query
    # =========================================================================
    
    async def search_transactions(
        self,
        query: str,
        page: int = 1
    ) -> List[Transaction]:
        """Search transactions with a query string."""
        client = await self._get_client()
        response = await client.get(
            "/search/transactions",
            params={"query": query, "page": page}
        )
        response.raise_for_status()
        
        transactions = []
        for item in response.json().get("data", []):
            attrs = item.get("attributes", {})
            splits = attrs.get("transactions", [{}])
            if not splits:
                continue
            split = splits[0]
            
            transactions.append(Transaction(
                id=int(item["id"]),
                type=TransactionType(split.get("type", "withdrawal")),
                date=date.fromisoformat(split.get("date", "2000-01-01")[:10]),
                amount=float(split.get("amount", 0)),
                description=split.get("description", ""),
                source_name=split.get("source_name", ""),
                destination_name=split.get("destination_name", ""),
                category_name=split.get("category_name"),
                budget_name=split.get("budget_name"),
                tags=split.get("tags", []),
                notes=split.get("notes")
            ))
        return transactions
    
    async def get_summary(
        self,
        start_date: date,
        end_date: date,
        currency_code: str = "USD"
    ) -> Dict[str, Any]:
        """Get a financial summary for a date range."""
        client = await self._get_client()
        response = await client.get(
            "/summary/basic",
            params={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "currency_code": currency_code
            }
        )
        response.raise_for_status()
        return response.json()


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_firefly_client() -> FireflyClient:
    """Get a configured Firefly client instance."""
    return FireflyClient()


async def quick_expense(
    amount: float,
    description: str,
    category: Optional[str] = None,
    source_account: str = "Checking Account"
) -> Transaction:
    """Quick helper to record an expense."""
    async with FireflyClient() as client:
        return await client.create_transaction(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=amount,
            description=description,
            source_account=source_account,
            destination_account=description,  # Creates expense account
            category=category
        )


async def quick_income(
    amount: float,
    description: str,
    category: Optional[str] = None,
    destination_account: str = "Checking Account"
) -> Transaction:
    """Quick helper to record income."""
    async with FireflyClient() as client:
        return await client.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            description=description,
            source_account=description,  # Creates revenue account
            destination_account=destination_account,
            category=category
        )
