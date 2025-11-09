import logging
from typing import List, Dict, Optional
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class GPTService:
    """
    Service for streaming responses from GPT.
    Handles conversation context and generates responses with low latency.
    """

    # Default system prompt for voice assistant
    DEFAULT_SYSTEM_PROMPT = """FUSION FIREWORKS - AI ASSISTANT SYSTEM PROMPT
ROLE & IDENTITY
You are Sofia, a friendly sales assistant for Fusion Fireworks in Surrey, BC. Keep responses brief and natural - answer questions and capture leads efficiently.
BUSINESS INFO
Company: Fusion Fireworks
Location: Surrey, BC, Canada
Phone: (778) 651-1633
Email: sales@fusionfireworks.ca
Instagram: @fusionfireworkscanada
Website: fusionfireworks.ca
What We Offer:

500+ consumer fireworks products
In-person shopping available
Up to 50% off promotions
Guaranteed Price Beat
Same-day/next-day pickup & delivery
Free shipping on Surrey orders $80+

Payment: Cash or e-transfer (payment machines temporarily down)
YOUR JOB
Do not say more than you are asked. Let the caller ask the questions.
Answer questions briefly
Capture contact info for anyone interested in placing an order
Transfer calls when needed (language barrier or urgent requests)

OPENING
"Hi! Thanks for calling Fusion Fireworks. I'm Sofia. How can I help you?"
LEAD CAPTURE
When someone wants to place an order, collect:

Full name
Phone number

Use captureInPersonLead function
After using the function call, let them know a team member will reach out to confirm

CALL TRANSFERS
Language Barrier:
"No problem! For help in another language please call 236 334 2808"
Urgent Requests or Complex Questions:
"Let me connect you with a team member right away - please call 236 334 2808"
QUICK ANSWERS
Location: "We're in Surrey, BC."
Products: "We have 500+ products - roman candles, cakes, sparklers, variety packs, and more."
Pricing: "Prices range from $2 to $137+. Most displays run $100-$500."
Online Orders: "Yes, we ship across Canada and offer local pickup."
Free Shipping: "Orders $350+ ship free across Canada. Surrey orders $80+ ship free."
Specific Products: "We likely have that! Can I grab your name and number so our team can confirm availability and help you place an order?"
TONE
Brief, friendly, helpful. No rambling. Answer what they ask, capture info if interested, move on. Do not start talking about our products or their interests"""

    def __init__(self, api_key: Optional[str] = None, system_prompt: Optional[str] = None):
        """
        Initialize the GPT service.

        Args:
            api_key: OpenAI API key. If None, uses settings.openai_api_key
            system_prompt: Custom system prompt. If None, uses DEFAULT_SYSTEM_PROMPT
        """
        self.api_key = api_key or settings.openai_api_key
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.enabled = bool(self.api_key)

        if self.enabled:
            logger.info("GPT service initialized successfully")
        else:
            logger.warning("GPT service initialized without API key")

    async def get_response(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        model: str = "gpt-4o-mini",
        max_completion_tokens: int = 150,
        stream: bool = True
    ) -> str:
        """
        Get a response from GPT.

        Args:
            user_input: The user's message
            conversation_history: Previous conversation messages (list of {role, content} dicts)
            model: OpenAI model to use
            max_completion_tokens: Maximum response length
            stream: Whether to stream the response

        Returns:
            The complete response text
        """
        if not self.enabled:
            logger.warning("GPT service not enabled - cannot get response")
            return "I'm sorry, I'm currently unavailable."

        try:
            # Build messages
            messages = [{"role": "system", "content": self.system_prompt}]

            # Add conversation history
            if conversation_history:
                messages.extend(conversation_history)

            # Add current user input
            messages.append({"role": "user", "content": user_input})

            logger.debug(f"[GPT] Sending request with {len(messages)} messages")

            if stream:
                return await self._stream_response(messages, model, max_completion_tokens)
            else:
                return await self._get_response(messages, model, max_completion_tokens)

        except Exception as e:
            logger.error(f"[GPT] Error getting response: {e}", exc_info=True)
            return "I'm sorry, I encountered an error. Please try again."

    async def _stream_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_completion_tokens: int
    ) -> str:
        """Stream response from GPT and return complete text."""
        response_text = ""
        chunk_count = 0

        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            stream=True
        )

        async for chunk in await stream:
            chunk_count += 1
            logger.debug(f"[GPT] Received chunk {chunk_count}: {chunk}")

            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and hasattr(delta, 'content') and delta.content:
                    content = delta.content
                    response_text += content
                    # Log streaming chunks at debug level
                    logger.debug(f"[GPT STREAM] {content}")
            else:
                logger.debug(f"[GPT] Chunk {chunk_count} has no choices")

        logger.info(f"[GPT] Stream complete: {chunk_count} chunks, {len(response_text)} characters")
        return response_text

    async def _get_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_completion_tokens: int
    ) -> str:
        """Get non-streaming response from GPT."""
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            stream=False
        )

        return response.choices[0].message.content

    def is_enabled(self) -> bool:
        """Check if the GPT service is enabled and ready."""
        return self.enabled

    def set_system_prompt(self, system_prompt: str):
        """Update the system prompt."""
        self.system_prompt = system_prompt
        logger.info("System prompt updated")

