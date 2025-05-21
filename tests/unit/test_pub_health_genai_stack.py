import aws_cdk as core
import aws_cdk.assertions as assertions

from pub_health_genai.pub_health_genai_stack import PubHealthGenaiStack

# example tests. To run these tests, uncomment this file along with the example
# resource in pub_health_genai/pub_health_genai_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = PubHealthGenaiStack(app, "pub-health-genai")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
