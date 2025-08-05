# stacks/main_stack.py
from typing import Any, Dict

from aws_cdk import Stack
from constructs import Construct

from .amazon_connect import Connect
from .aurora_knowledge_base import AuroraKnowledgeBase
from .lambda_lex_bot import LambdaAndLexBot


class RagChatbotStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        database_name: str,
        knowledge_base_name: str,
        embeddings_model_id: str,
        bedrock_model_id: str,
        chunking_strategy: str,
        chunking_config: Dict[str, Any],
        environment: str,
        chat_welcome_prompt: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Knowledge Base
        kb_component = AuroraKnowledgeBase(
            self,
            "AuroraKnowledgeBase",
            database_name=database_name,
            knowledge_base_name=knowledge_base_name,
            embeddings_model_id=embeddings_model_id,
            chunking_strategy=chunking_strategy,
            chunking_config=chunking_config,
            account_id=self.account,
            region=self.region,
        )

        # Create Lex Bot
        lex_component = LambdaAndLexBot(
            self,
            "LambdaAndLexBot",
            knowledge_base_id=kb_component.knowledge_base_id,
            bedrock_model_id=bedrock_model_id,
            account_id=self.account,
            region=self.region,
        )

        # Create Connect Instance
        connect_component = Connect(
            self,
            "Connect",
            environment=environment,
            lex_bot_id=lex_component.lex_bot_id,
            chat_welcome_prompt=chat_welcome_prompt,
            account_id=self.account,
            region=self.region,
            stack_name=self.stack_name,
        )
