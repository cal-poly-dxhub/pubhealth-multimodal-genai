#!/usr/bin/env python3

import aws_cdk as cdk

from cdk.knowledge_base import RagKnowledgeBaseStack
from cdk.opensearch_serverless import
app = cdk.App()
RagKnowledgeBaseStack(
    app,
    "RagKnowledgeBaseStack",
)
OpenSearchServerlessStack(
    app,
    "OpenSearchServerlessStack",
)
app.synth()
