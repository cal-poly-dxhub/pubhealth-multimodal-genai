import json
import os

import boto3

bedrockClient = boto3.client("bedrock-agent")


def lambda_handler(event, context):
    dataSourceId = os.environ["DATASOURCEID"]
    knowledgeBaseId = os.environ["KNOWLEDGEBASEID"]
    # Check for in-progress ingestion jobs
    try:
        list_response = bedrockClient.list_ingestion_jobs(
            dataSourceId=dataSourceId,
            knowledgeBaseId=knowledgeBaseId,
            filters=[
                {
                    "attribute": "STATUS",
                    "operator": "EQ",
                    "values": ["IN_PROGRESS"],
                }
            ],
        )
        # Check if the ingestionJobSummaries list is empty
        if list_response.get("ingestionJobSummaries"):
            print("There are ingestion jobs currently in progress.")
            return {
                "statusCode": 200,
                "body": json.dumps("Ingestion job already in progress."),
            }
    except Exception as e:
        print("Error checking ingestion jobs: ", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps("Error checking ingestion jobs: " + str(e)),
        }
    # Start a new ingestion job if no jobs are in progress
    try:
        response = bedrockClient.start_ingestion_job(
            knowledgeBaseId=knowledgeBaseId, dataSourceId=dataSourceId
        )
        print("Ingestion Job Response: ", response)
        return {
            "statusCode": 200,
            "body": json.dumps("Ingestion job started successfully."),
        }
    except Exception as e:
        print("Error starting ingestion job: ", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps("Error starting ingestion job: " + str(e)),
        }
