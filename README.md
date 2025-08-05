# RAG Serverless Chatbot Solution


## Table of Contents
- [Collaboration](#collaboration)
- [Disclaimers](#disclaimers)
- [Overview](#chatbot-overview)
- [Deployment Steps](#deployment-steps)



# Collaboration
Thanks for your interest in our solution.  Having specific examples of replication and cloning allows us to continue to grow and scale our work. If you clone or download this repository, kindly shoot us a quick email to let us know you are interested in this work!

[wwps-cic@amazon.com]

# Disclaimers

**Customers are responsible for making their own independent assessment of the information in this document.**

**This document:**

(a) is for informational purposes only,

(b) represents current AWS product offerings and practices, which are subject to change without notice, and

(c) does not create any commitments or assurances from AWS and its affiliates, suppliers or licensors. AWS products or services are provided “as is” without warranties, representations, or conditions of any kind, whether express or implied. The responsibilities and liabilities of AWS to its customers are controlled by AWS agreements, and this document is not part of, nor does it modify, any agreement between AWS and its customers.

(d) is not to be considered a recommendation or viewpoint of AWS

**Additionally, all prototype code and associated assets should be considered:**

(a) as-is and without warranties

(b) not suitable for production environments

(d) to include shortcuts in order to support rapid prototyping such as, but not limitted to, relaxed authentication and authorization and a lack of strict adherence to security best practices

**All work produced is open source. More information can be found in the GitHub repo.**

## Authors
- Venkata Kampana - kampanav@amazon.com
- Nick Riley - njriley@calpoly.edu

## Deployment Steps

### Prerequisites
- AWS CDK CLI
- Docker
- Python 3.x
- AWS credentials
- Bedrock model access
- Git

Configure AWS Credentials and Region with an Access key
```bash
aws configure
```

Clone the repo:
```bash
git clone https://github.com/cal-poly-dxhub/pubhealth-multimodal-genai.git
```

Rename example config file:
```bash
mv example_config.yaml config.yaml
```
Fill in config with your AWS values.

Install `requirements.txt`:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

### 1. Infrastructure Deployment
```bash

# Synthesize the template
cdk synth

# Deploy the stack
cdk deploy
```

### 2. File Upload to S3
Upload local files to S3 bucket with the name:
`<stack_name>-ragdatabucket-<uuid>`

This will trigger the knowledge base to sync and ingest the new documents.
Syncing may take a few minutes to an hour depending on data size.
To view this progress go to the bedrock knowledge base console.

### 3. Create Amazon Connect Widget
You can find the [instructions to configure the widget here](https://docs.aws.amazon.com/connect/latest/adminguide/config-com-widget1.html).
For a chatbot only experience: Use the provided BasicChatFlow and Enable text only.

### 4. Testing
Once document ingestion is complete, you can test the system in Amazon Connect.

## Troubleshooting
- Ensure docker is running and you have access to it
- Verify AWS credentials are properly configured
- Ensure all required dependencies are installed
- If encountering throttling errors, try changing the chat model
- Please reach out to the authors for further questions

**Note:** The Database, DynamoDB Table, and S3 Bucket are set to DESTROY, so they will be deleted if the stack gets destroyed. To keep these in the event the stack gets destroyed, set RemovalPolicy to RETAIN.

## Cost
| Component | 1K Messages | 10K Messages | 100K Messages |
|-----------|------------|-------------|--------------|
| Claude 3 Haiku | | | | |
| Input tokens | $0.05 | $0.50 | $5.00 |
| Output tokens | $0.13 | $1.25 | $12.50 |
| Amazon Lex | | | | |
| Text requests | $0.75 | $7.50 | $75.00 |
| Amazon Connect | | | | |
| Chat messages | $4.00 | $40.00 | $400.00 |
| Aurora pgvector | | | | |
| Compute (ACUs) | $43.80 | $87.60 | $175.20 |
| Storage | $0.10 | $0.20 | $0.50 | $2.00 |
| Total Monthly Cost | $48.83 | $137.05 | $668.20 |

**Disclaimer:** This is only an estimate, pricing varies on user behaviour and traffic.


## Support
For any queries or issues, please contact:
- Venkata Kampana, Sr Solutions Architect - kampanv@amazon.com
- Nick Riley, Jr. SDE - njriley@calpoly.edu
