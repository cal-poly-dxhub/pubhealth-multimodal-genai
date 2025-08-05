import logging
import os

import boto3
import cfnresponse

client = boto3.client("connect")

LOG_LEVEL = os.getenv("LOG_LEVEL")
INSTANCE_ID = os.getenv("INSTANCE_ID")


def lambda_handler(event, context):
    global log_level
    log_level = str(LOG_LEVEL).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "ERROR"
    logging.getLogger().setLevel(log_level)

    logging.info(f"Event: {event}")

    request_type = event["RequestType"]

    if request_type == "Delete":
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        return

    if request_type in {"Create", "Update"}:
        try:
            contact_queue_name = event["ResourceProperties"]["ContactQueueName"]
            contact_queue_types = event["ResourceProperties"][
                "ContactQueueTypes"
            ]

            marker = None

            while True:
                paginator = client.get_paginator("list_queues")
                response_iterator = paginator.paginate(
                    InstanceId=INSTANCE_ID,
                    QueueTypes=contact_queue_types,
                    PaginationConfig={"PageSize": 10, "StartingToken": marker},
                )
                for page in response_iterator:
                    contact_queues = page["QueueSummaryList"]
                    for contact_queue in contact_queues:
                        if contact_queue["Name"] == contact_queue_name:
                            response_data = {
                                "ContactQueueId": contact_queue["Id"],
                                "ContactQueueArn": contact_queue["Arn"],
                            }
                            cfnresponse.send(
                                event,
                                context,
                                cfnresponse.SUCCESS,
                                response_data,
                            )
                            return
                try:
                    marker = response_iterator["Marker"]
                except Exception as e:
                    logging.error(e)
                    cfnresponse.send(
                        event,
                        context,
                        cfnresponse.FAILED,
                        {"message": f"ERROR: {e}"},
                    )
                    break
        except Exception as e:
            logging.error(e)
            cfnresponse.send(
                event, context, cfnresponse.FAILED, {"message": f"ERROR: {e}"}
            )
            return
