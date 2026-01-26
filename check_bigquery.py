"""
BigQuery Data Checker - Run this to see what data is saved in BigQuery
"""
from google.cloud import bigquery
import os

# Set credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '.secrets/leadpilot-gdg-ae42d1864e6a.json'

def check_bigquery():
    client = bigquery.Client(project='leadpilot-gdg')
    
    print('=' * 70)
    print('🔍 BIGQUERY DATA CHECK - LeadPilot')
    print('=' * 70)
    
    # List datasets
    print('\n📂 DATASETS in project "leadpilot-gdg":')
    datasets = list(client.list_datasets())
    if datasets:
        for ds in datasets:
            print(f'   ✓ {ds.dataset_id}')
    else:
        print('   (No datasets found)')
    
    # Check for our table
    print('\n📋 TABLES in "leadpilot_dataset":')
    try:
        tables = list(client.list_tables('leadpilot_dataset'))
        if tables:
            for table in tables:
                print(f'   ✓ {table.table_id}')
        else:
            print('   (No tables found - will be created on first lead)')
    except Exception as e:
        print(f'   ⚠️ Dataset not found yet: {e}')
        print('   → Dataset will be created when you process your first lead!')
        return
    
    # Query all data
    print('\n📊 DATA in "business_leads" table:')
    print('-' * 70)
    try:
        query = '''
        SELECT 
            lead_id,
            user_id,
            user_email,
            user_name,
            status,
            business_name,
            business_phone,
            business_email,
            business_city,
            business_category,
            research_priority,
            email_sent,
            created_at,
            updated_at
        FROM leadpilot_dataset.business_leads
        ORDER BY created_at DESC
        '''
        results = client.query(query).result()
        rows = list(results)
        
        if rows:
            print(f'   Found {len(rows)} lead(s):\n')
            for i, row in enumerate(rows, 1):
                print(f'   {i}. {row.business_name}')
                print(f'      └─ Status: {row.status}')
                print(f'      └─ User: {row.user_email or row.user_id or "anonymous"}')
                print(f'      └─ City: {row.business_city}')
                print(f'      └─ Category: {row.business_category}')
                print(f'      └─ Priority: {row.research_priority}')
                print(f'      └─ Email Sent: {row.email_sent}')
                print(f'      └─ Created: {row.created_at}')
                print()
        else:
            print('   📭 No leads saved yet!')
            print()
            print('   To save data, do the following in the app:')
            print('   1. Search for leads in a city')
            print('   2. Click "View Details" → "Send to SDR"')
            print('   3. Click "Confirm Lead" or "Send Email"')
            print()
            
    except Exception as e:
        print(f'   ⚠️ Error querying data: {e}')
    
    # Show table schema
    print('\n📐 TABLE SCHEMA:')
    print('-' * 70)
    try:
        table = client.get_table('leadpilot_dataset.business_leads')
        for field in table.schema:
            print(f'   {field.name}: {field.field_type}')
    except:
        print('   (Table not created yet)')
    
    print('\n' + '=' * 70)

if __name__ == '__main__':
    check_bigquery()
