"""HubSpot CRM wrapper. Writes contacts and conversation events."""
import os
from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInputForCreate
from dotenv import load_dotenv

load_dotenv()

_client = HubSpot(access_token=os.getenv("HUBSPOT_TOKEN"))


def upsert_contact(email: str, props: dict | None = None) -> str:
    """Create or update a contact. Returns HubSpot contact ID."""
    properties = {"email": email}
    if props:
        properties.update(props)
    contact = _client.crm.contacts.basic_api.create(
        SimplePublicObjectInputForCreate(properties=properties)
    )
    return contact.id
