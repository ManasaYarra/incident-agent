import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

client = Hindsight(
    base_url="https://api.hindsight.vectorize.io",
    api_key=os.getenv("HINDSIGHT_API_KEY")
)

BANK_ID = "incident-response"  # must match exactly what you named it on the dashboard

def save_incident(log, root_cause, fix, outcome):
    text = f"Error: {log}\nRoot cause: {root_cause}\nFix: {fix}\nOutcome: {outcome}"
    return client.retain(bank_id=BANK_ID, content=text)

def find_similar(new_log):
    return client.recall(bank_id=BANK_ID, query=new_log)