"""
This script configures the local Pub/Sub emulator.

It creates the topic and the push subscription, pointing
it to the local processing service (backend).

Run this from Terminal 3 after starting the emulator (T1)
and the backend service (T2).
"""

import os
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.types import PushConfig
from google.api_core.exceptions import AlreadyExists

from dotenv import load_dotenv

# Cloud Run assets K_SERVICE. If it is not present, is locally env
IS_LOCAL = os.environ.get("K_SERVICE") is None

if IS_LOCAL: # then load .env file
    dotenv_path = os.path.join(os.path.dirname(__file__), "../project_env/keys.env")
    load_dotenv(dotenv_path=dotenv_path, override=False)

# --- Configuration ---
PROJECT_ID = "local-test-project"  # This MUST match the emulator's project
TOPIC_NAME = "fit-file-processing-topic"
SUBSCRIPTION_NAME = "local-processing-sub"
# This is the URL of your backend service (running in Terminal 2)
PUSH_ENDPOINT = "http://localhost:8081/pubsub-processing-handler"
# ---------------------
host = os.environ.get("PUBSUB_EMULATOR_HOST")
print(host)
# Verify that the emulator host is set in the environment
if not os.environ.get("PUBSUB_EMULATOR_HOST"):
    print("Error: PUBSUB_EMULATOR_HOST environment variable is not set.")
    print("Please run: export PUBSUB_EMULATOR_HOST=\"localhost:8085\"")
    exit(1)

print("Emulator host detected. Connecting to local emulator...")

# Setup clients
subscriber = pubsub_v1.SubscriberClient()
publisher = pubsub_v1.PublisherClient()


# 1. Create the Topic
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)
try:
    publisher.create_topic(request={"name": topic_path})
    print(f"✅ Topic created: {TOPIC_NAME}")
except AlreadyExists:
    print(f"✅ Topic already exists: {TOPIC_NAME}")
except Exception as e:
    print(f"Error creating topic: {e}")
    exit(1)

# 2. Create the Push Subscription
subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_NAME)
# push_config = (pubsub_v1.types.PushConfig(push_endpoint=PUSH_ENDPOINT))

try:
    subscriber.create_subscription(
        request={
            "name": subscription_path,
            "topic": topic_path,
            "push_config": {"push_endpoint": PUSH_ENDPOINT},
            "ack_deadline_seconds": 600,
        }
    )
    print(f"✅ Subscription created: {SUBSCRIPTION_NAME}")
    print(f"   ...pushing to {PUSH_ENDPOINT}")
except AlreadyExists:
    print(f"✅ Subscription already exists: {SUBSCRIPTION_NAME}")
except Exception as e:
    print(f"Error creating subscription: {e}")
    print("This often fails if the push endpoint is not running.")
    print(f"Ensure your backend is running at {PUSH_ENDPOINT}")
    exit(1)

print("\nEmulator setup complete. You can now start the frontend service.")