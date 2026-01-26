"""
Fix BigQuery Table - Recreate with proper schema
"""
from google.cloud import bigquery
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '.secrets/leadpilot-gdg-ae42d1864e6a.json'

client = bigquery.Client(project='leadpilot-gdg')

# Delete the table without schema and recreate it
table_id = 'leadpilot-gdg.leadpilot_dataset.business_leads'

print('Deleting old table...')
try:
    client.delete_table(table_id)
    print('Old table deleted')
except:
    print('Table did not exist')

# Create with proper schema
print('Creating table with schema...')
schema = [
    bigquery.SchemaField('lead_id', 'STRING', mode='REQUIRED'),
    bigquery.SchemaField('user_id', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('user_email', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('user_name', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('status', 'STRING', mode='REQUIRED'),
    bigquery.SchemaField('business_name', 'STRING', mode='REQUIRED'),
    bigquery.SchemaField('business_phone', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('business_email', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('business_address', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('business_city', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('business_category', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('business_rating', 'FLOAT64', mode='NULLABLE'),
    bigquery.SchemaField('research_summary', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('research_industry', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('research_priority', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('meeting_date', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('meeting_time', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('meeting_calendar_link', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('email_sent', 'BOOLEAN', mode='NULLABLE'),
    bigquery.SchemaField('email_sent_at', 'TIMESTAMP', mode='NULLABLE'),
    bigquery.SchemaField('email_subject', 'STRING', mode='NULLABLE'),
    bigquery.SchemaField('created_at', 'TIMESTAMP', mode='REQUIRED'),
    bigquery.SchemaField('updated_at', 'TIMESTAMP', mode='REQUIRED'),
    bigquery.SchemaField('status_changed_at', 'TIMESTAMP', mode='NULLABLE'),
]

table = bigquery.Table(table_id, schema=schema)
table = client.create_table(table)
print(f'Table {table.table_id} created with {len(schema)} columns')
print('')
print('Data will be saved to:')
print(f'   Project: leadpilot-gdg')
print(f'   Dataset: leadpilot_dataset')
print(f'   Table:   business_leads')
print(f'   Location: {table.location}')
print('')
print('Table is ready! Now process a lead in the app to save data.')
