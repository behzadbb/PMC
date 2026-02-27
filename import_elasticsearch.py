from elasticsearch import Elasticsearch, helpers
import re
import pandas as pd
from tqdm import tqdm
from sqlalchemy import create_engine

elasticHost = "https://search.bregulator.com"
header_Authorization_token = "SWFxUkQ0MEJhSVY1U2YyMElBT3A6ekEzUGlHNWlSaS13LXJuTV9SQ21kQQ=="

es = Elasticsearch(
    "https://search.bregulator.com",
    api_key="SWFxUkQ0MEJhSVY1U2YyMElBT3A6ekEzUGlHNWlSaS13LXJuTV9SQ21kQQ==",
    verify_certs=True
)

index_name = "articles_demo"
mapping = {
    "mappings": {
        "properties": {
            "Title": {"type": "text"},
            "Abstract": {"type": "text"},
            "Text": {"type": "text"},
            "SegmentId": {"type": "integer"},
            "BookId": {"type": "integer"}
        }
    }
}

# Create index
if not es.indices.exists(index=index_name):
    es.indices.create(index=index_name, body=mapping)
    print(f"Index '{index_name}' created.")
else:
    print(f"Index '{index_name}' already exists.")
    

host = "mssql-db"
port = 1433
username = "sa"
password = "bReg@HetzPasSw0rd"
dbname = "EastPharmaDB_test"

connection_string = (
    f"mssql+pyodbc://{username}:{password}@{host},{port}/{dbname}"
    "?driver=ODBC+Driver+18+for+SQL+Server"
)
engine = create_engine(connection_string)
# خواندن داده‌ها با Pandas
query = '''
SELECT seg.SegmentId, seg.Title, b.Summary, seg.Text, seg.BookId
FROM Segments AS seg
JOIN Books AS b ON b.BookId = seg.BookId
'''
df = pd.read_sql_query(query, engine)
print(f"Loaded {len(df)} rows from SQL Server")

def generate_actions(df):
    for _, row in df.iterrows():
        yield {
            "_index": index_name,
            "_id": row["SegmentId"],  # استفاده از SegmentId به عنوان _id
            "_source": {
                "Title": row["Title"],
                "Abstract": row["Summary"],
                "Text": row["Text"],
                "SegmentId": row["SegmentId"],
                "BookId": row["BookId"]
            }
        }


for success, info in tqdm(
    helpers.streaming_bulk(es, generate_actions(df), chunk_size=1000),
    total=len(df),
):
    if not success:
        print("Failed to index:", info)

print("✅ Bulk import completed.")