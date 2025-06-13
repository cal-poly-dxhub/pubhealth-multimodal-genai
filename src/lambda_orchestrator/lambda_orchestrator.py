import json
import logging
import os
import pprint

import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_session_attributes(intent_request):
    session_state = intent_request["sessionState"]
    return session_state.get("sessionAttributes", {})


def close(intent_request, session_attributes, fulfillment_state, message):
    response = {
        "sessionState": {
            "sessionAttributes": session_attributes,
            "dialogAction": {"type": "Close"},
            "intent": intent_request["sessionState"]["intent"],
        },
        "messages": [message],
        "sessionId": intent_request["sessionId"],
    }
    response["sessionState"]["intent"]["state"] = fulfillment_state
    logger.debug(
        '<<help_desk_bot>> "Lambda fulfillment function response = \n'
        + pprint.pformat(response, indent=4)
    )
    return response


def hello_intent_handler(intent_request, session_attributes):
    # Clear out session attributes to start new
    session_attributes = {}
    response_string = "Hello! How can we help you today?"
    return close(
        intent_request,
        session_attributes,
        "Fulfilled",
        {"contentType": "PlainText", "content": response_string},
    )


def retrieve_and_generate(input_text, kb_id, arn, session_id):
    bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
    if session_id:
        logger.debug(session_id)
        return bedrock_agent_runtime.retrieve_and_generate(
            sessionId=session_id,
            input={"text": input_text},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": arn,
                },
            },
        )
    else:
        logger.debug("no session ID")
        return bedrock_agent_runtime.retrieve_and_generate(
            input={"text": input_text},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": arn,
                },
            },
        )


def retrieve_knowledge_base_session(session_id):
    table_name = os.environ["DDB_Name"]
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    try:
        response = table.get_item(Key={"SessionID_Lex": session_id})
        column_value = response.get("Item", {}).get("kbsession")
        return column_value
    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def update_knowledge_base_session(session_id, kb_session):
    table_name = os.environ["DDB_Name"]
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    update_attribute_name = "kbsession"
    try:
        response = table.update_item(
            Key={"SessionID_Lex": session_id},
            UpdateExpression=f"SET {update_attribute_name} = :val",
            ExpressionAttributeValues={":val": kb_session},
            ReturnValues="UPDATED_NEW",
        )
        updated_attributes = response.get("Attributes", {})
        return {
            "statusCode": 200,
            "body": {"UpdatedAttributes": updated_attributes},
        }
    except Exception as e:
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def fallback_intent_handler(intent_request, session_attributes):
    query_string = intent_request["transcriptions"][0]["transcription"]
    kb_id = os.environ["KBID"]
    arn = os.environ["MODEL_ARN"]
    session_id = intent_request["sessionId"]
    logger.debug(
        '<<help_desk_bot>> fallback_intent_handler(): calling retrieve_and_generate(query="%s")',
        query_string,
    )
    kb_session = retrieve_knowledge_base_session(session_id)
    response = retrieve_and_generate(query_string, kb_id, arn, kb_session)
    generated_kbsession = response["sessionId"]
    generated_text = response["output"]["text"]
    kb_session = update_knowledge_base_session(session_id, generated_kbsession)
    if generated_text is None:
        generated_text = "Sorry, I was not able to understand your question."
        return close(
            intent_request,
            session_attributes,
            "Fulfilled",
            {"contentType": "PlainText", "content": generated_text},
        )
    else:
        logger.debug(
            '<<help_desk_bot>> "fallback_intent_handler(): kendra_response = %s',
            generated_text,
        )
        return close(
            intent_request,
            session_attributes,
            "Fulfilled",
            {"contentType": "PlainText", "content": generated_text},
        )


def lambda_handler(event, context):
    logger.debug("<<help_desk_bot>> Lex event info = " + json.dumps(event))
    session_attributes = get_session_attributes(event)
    logger.debug(
        "<<help_desk_bot> lambda_handler: session_attributes = "
        + json.dumps(session_attributes)
    )
    current_intent = event["sessionState"]["intent"]["name"]
    if current_intent is None:
        response_string = "Sorry, I didn't understand."
        return close(
            session_attributes,
            current_intent,
            "Fulfilled",
            {"contentType": "PlainText", "content": response_string},
        )
    intent_name = current_intent
    if intent_name is None:
        response_string = "Sorry, I didn't understand."
        return close(
            session_attributes,
            intent_name,
            "Fulfilled",
            {"contentType": "PlainText", "content": response_string},
        )
    # See HANDLERS dict at the bottom
    if HANDLERS.get(intent_name, False):
        return HANDLERS[intent_name]["handler"](
            event, session_attributes
        )  # Dispatch to the event handler
    else:
        response_string = "The intent " + intent_name + " is not yet supported."
        return close(
            session_attributes,
            intent_name,
            "Fulfilled",
            {"contentType": "PlainText", "content": response_string},
        )


# List of intent handler functions for the dispatch process
HANDLERS = {
    "greeting_intent": {"handler": hello_intent_handler},
    "FallbackIntent": {"handler": fallback_intent_handler},
}
