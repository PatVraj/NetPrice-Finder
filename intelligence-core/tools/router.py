"""
SSIP - Sovereign Smart Intelligence Platform
Intelligence Core - Semantic Router

This module provides intent classification and tool routing
using local LLM (Ollama) with function calling.
"""

import os
import json
from typing import Optional, Dict, Any, List
import httpx
from pydantic import BaseModel
import structlog

# Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.1:8b")

logger = structlog.get_logger()

# =============================================================================
# Models
# =============================================================================

class ToolCall(BaseModel):
    """Represents a tool/function call from the LLM."""
    tool: str
    parameters: Dict[str, Any]
    confidence: float = 1.0

class RouterResult(BaseModel):
    """Result from the semantic router."""
    intent: str
    tool_call: Optional[ToolCall] = None
    raw_response: str

# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS = [
    {
        "name": "scrape_url",
        "description": "Navigate to a specific URL and extract content",
        "parameters": {
            "url": {"type": "string", "required": True}
        }
    },
    {
        "name": "check_cashback",
        "description": "Check current cashback rates for a store across all portals",
        "parameters": {
            "store_name": {"type": "string", "required": True}
        }
    },
    {
        "name": "query_transactions",
        "description": "Search user's transaction history in Firefly III",
        "parameters": {
            "start_date": {"type": "string", "required": False},
            "end_date": {"type": "string", "required": False},
            "category": {"type": "string", "required": False},
            "merchant": {"type": "string", "required": False}
        }
    },
    {
        "name": "parse_document",
        "description": "Parse a bank statement PDF using vision model",
        "parameters": {
            "file_path": {"type": "string", "required": True}
        }
    },
    {
        "name": "optimize_card",
        "description": "Recommend the optimal credit card for a purchase",
        "parameters": {
            "merchant": {"type": "string", "required": True},
            "amount": {"type": "number", "required": False}
        }
    },
    {
        "name": "chat",
        "description": "General conversation or question answering",
        "parameters": {
            "message": {"type": "string", "required": True}
        }
    }
]

# =============================================================================
# Semantic Router
# =============================================================================

class SemanticRouter:
    """
    Routes user commands to appropriate tools using LLM function calling.
    """
    
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for intent classification."""
        tools_desc = "\n".join([
            f"- {t['name']}: {t['description']}"
            for t in TOOLS
        ])
        
        return f"""You are a semantic router for a financial intelligence platform.
Your job is to analyze user commands and select the appropriate tool to handle them.

Available tools:
{tools_desc}

Rules:
1. If the input is a URL (starts with http:// or https://), use scrape_url
2. If the user asks about cashback, rewards, or deals for a store, use check_cashback
3. If the user asks about their spending, transactions, or financial history, use query_transactions
4. If the user mentions uploading or parsing a document/PDF/statement, use parse_document
5. If the user asks which card to use or about optimizing rewards, use optimize_card
6. For general questions or conversation, use chat

You MUST respond with valid JSON in this exact format:
{{"tool": "tool_name", "parameters": {{"param1": "value1"}}}}

Only output the JSON, nothing else."""

    async def route(self, user_input: str) -> RouterResult:
        """
        Route a user command to the appropriate tool.
        
        Args:
            user_input: The user's command or query
            
        Returns:
            RouterResult with intent and tool call
        """
        # Quick check for URLs
        if user_input.strip().startswith(('http://', 'https://')):
            return RouterResult(
                intent="scrape_url",
                tool_call=ToolCall(
                    tool="scrape_url",
                    parameters={"url": user_input.strip()},
                    confidence=1.0
                ),
                raw_response=""
            )
        
        # Use LLM for intent classification
        try:
            response = await self.client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"User command: {user_input}",
                    "system": self._build_system_prompt(),
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 200
                    }
                }
            )
            
            if response.status_code != 200:
                logger.error("Ollama request failed", status=response.status_code)
                return self._fallback_routing(user_input)
            
            result = response.json()
            raw_response = result.get("response", "").strip()
            
            # Parse JSON response
            try:
                # Try to extract JSON from the response
                json_str = raw_response
                if "```" in json_str:
                    # Extract from code block
                    json_str = json_str.split("```")[1]
                    if json_str.startswith("json"):
                        json_str = json_str[4:]
                
                parsed = json.loads(json_str)
                tool_name = parsed.get("tool", "chat")
                parameters = parsed.get("parameters", {})
                
                return RouterResult(
                    intent=tool_name,
                    tool_call=ToolCall(
                        tool=tool_name,
                        parameters=parameters,
                        confidence=0.9
                    ),
                    raw_response=raw_response
                )
                
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON", response=raw_response)
                return self._fallback_routing(user_input, raw_response)
                
        except Exception as e:
            logger.error("Router error", error=str(e))
            return self._fallback_routing(user_input)
    
    def _fallback_routing(self, user_input: str, raw_response: str = "") -> RouterResult:
        """Fallback routing using simple keyword matching."""
        input_lower = user_input.lower()
        
        # Keyword-based routing
        if any(kw in input_lower for kw in ["cashback", "reward", "deal", "rate"]):
            # Extract store name (simple heuristic)
            words = user_input.split()
            store_name = words[-1] if words else "unknown"
            return RouterResult(
                intent="check_cashback",
                tool_call=ToolCall(
                    tool="check_cashback",
                    parameters={"store_name": store_name},
                    confidence=0.5
                ),
                raw_response=raw_response
            )
        
        if any(kw in input_lower for kw in ["transaction", "spent", "spending", "purchase"]):
            return RouterResult(
                intent="query_transactions",
                tool_call=ToolCall(
                    tool="query_transactions",
                    parameters={},
                    confidence=0.5
                ),
                raw_response=raw_response
            )
        
        if any(kw in input_lower for kw in ["upload", "pdf", "statement", "parse", "document"]):
            return RouterResult(
                intent="parse_document",
                tool_call=ToolCall(
                    tool="parse_document",
                    parameters={"file_path": ""},
                    confidence=0.5
                ),
                raw_response=raw_response
            )
        
        if any(kw in input_lower for kw in ["card", "which card", "optimize", "best card"]):
            return RouterResult(
                intent="optimize_card",
                tool_call=ToolCall(
                    tool="optimize_card",
                    parameters={"merchant": ""},
                    confidence=0.5
                ),
                raw_response=raw_response
            )
        
        # Default to chat
        return RouterResult(
            intent="chat",
            tool_call=ToolCall(
                tool="chat",
                parameters={"message": user_input},
                confidence=0.3
            ),
            raw_response=raw_response
        )

# =============================================================================
# Utility Functions
# =============================================================================

async def check_ollama_health() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_HOST}/api/version")
            return response.status_code == 200
    except Exception:
        return False

async def list_models() -> List[str]:
    """List available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.error("Failed to list models", error=str(e))
    return []

async def pull_model(model_name: str) -> bool:
    """Pull a model from Ollama registry."""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/pull",
                json={"name": model_name},
                timeout=300.0
            )
            return response.status_code == 200
    except Exception as e:
        logger.error("Failed to pull model", model=model_name, error=str(e))
    return False

# =============================================================================
# Main (for testing)
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def test_router():
        router = SemanticRouter()
        
        test_inputs = [
            "https://www.nike.com/shoes",
            "What's the best cashback for Nike?",
            "How much did I spend last month?",
            "Upload my bank statement",
            "Which card should I use at Costco?",
            "Hello, how are you?"
        ]
        
        print("Testing Semantic Router\n" + "=" * 50)
        
        for user_input in test_inputs:
            result = await router.route(user_input)
            print(f"\nInput: {user_input}")
            print(f"Intent: {result.intent}")
            print(f"Tool: {result.tool_call.tool if result.tool_call else 'None'}")
            print(f"Params: {result.tool_call.parameters if result.tool_call else {}}")
        
        await router.close()
    
    asyncio.run(test_router())
