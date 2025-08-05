#!/usr/bin/env python3

from enum import Enum

import aws_cdk as cdk
import yaml

from cdk.main import RagChatbotStack


class CommunicationChannels(Enum):
    CHAT_ONLY = "chat_only"
    VOICE_ONLY = "voice_only"
    CHAT_AND_VOICE = "chat_and_voice"
    CHAT_VOICE_AND_SMS = "chat_voice_and_sms"


def create_app():
    CONFIG_PATH = "./config.yaml"
    config = yaml.safe_load(open(CONFIG_PATH))

    database_name = config["database_name"]
    knowledge_base_name = config["knowledge_base_name"]
    embeddings_model_id = config["embeddings_model_id"]
    bedrock_model_id = config["bedrock_model_id"]
    chunking_strategy = config["chunking_strategy"]

    # Create base configuration dict with all parameters as default values
    chunking_config = {
        "overlap_tokens": 60,
        "max_tokens": 300,
        "max_parent_tokens": 1500,
        "max_child_tokens": 300,
        "overlap_percentage": 15,
        "breakpoint_percentile_threshold": 90,
        "buffer_size": 0,
    }

    # Update parameters based on chunking strategy
    if chunking_strategy == "HIERARCHICAL":
        chunking_config.update(
            {
                "overlap_tokens": config["hierarchical"]["overlap_tokens"],
                "max_parent_tokens": config["hierarchical"][
                    "max_parent_tokens"
                ],
                "max_child_tokens": config["hierarchical"]["max_child_tokens"],
            }
        )
    elif chunking_strategy == "FIXED_SIZE":
        chunking_config.update(
            {
                "max_tokens": config["fixed_size"]["max_tokens"],
                "overlap_percentage": config["fixed_size"][
                    "overlap_percentage"
                ],
            }
        )
    elif chunking_strategy == "SEMANTIC":
        chunking_config.update(
            {
                "max_tokens": config["semantic"]["max_tokens"],
                "breakpoint_percentile_threshold": config["semantic"][
                    "breakpoint_percentile_threshold"
                ],
                "buffer_size": config["semantic"]["buffer_size"],
            }
        )

    app = cdk.App()

    RagChatbotStack(
        app,
        "RagChatbotStack",
        database_name=database_name,
        knowledge_base_name=knowledge_base_name,
        embeddings_model_id=embeddings_model_id,
        bedrock_model_id=bedrock_model_id,
        chunking_strategy=chunking_strategy,
        chunking_config=chunking_config,
        environment=config["environment"],
        chat_welcome_prompt=config["chat_welcome_prompt"],
    )

    app.synth()


if __name__ == "__main__":
    create_app()
