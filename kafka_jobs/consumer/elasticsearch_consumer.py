import sys
sys.path.append(".")

import time
import json
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, when
from pyspark.sql.types import StructType, StringType, IntegerType

from dotenv import load_dotenv
load_dotenv()

import os
os.environ['PYSPARK_SUBMIT_ARGS'] = '--jars ~/Documents/IT4043E_Group3_Problem3/jars/elasticsearch-spark-30_2.12-8.11.3.jar pyspark-shell'
KAFKA_URL = os.getenv("KAFKA_URL")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
ELASTICSEARCH_USER = os.getenv("ELASTICSEARCH_USER")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

from logger.logger import get_logger
logger = get_logger("elasticsearch_consumer")

def value_deserializer_func(data):
    return json.loads(data.decode('utf-8'))

class Consumer():
    def __init__(self):

        # spark session
        self._spark = SparkSession.builder \
                                .master("local") \
                                .appName("ParquetToElasticsearch") \
                                .config("spark.jars",
                                        "jars/gcs-connector-hadoop3-latest,jars/elasticsearch-spark-30_2.12-8.9.1") \
                                .config("spark.jars.packages",
                                        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.elasticsearch:elasticsearch-spark-30_2.12:8.9.1") \
                                .getOrCreate()

        self._spark._jsc.hadoopConfiguration().set("google.cloud.auth.service.account.json.keyfile", GOOGLE_APPLICATION_CREDENTIALS)
        self._spark._jsc.hadoopConfiguration().set('fs.gs.impl', 'com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem')
        self._spark._jsc.hadoopConfiguration().set('fs.gs.auth.service.account.enable', 'true')

        self._spark._jsc.hadoopConfiguration().set("fs.gs.outputstream.upload.buffer.size", "262144");
        self._spark._jsc.hadoopConfiguration().set("fs.gs.outputstream.upload.chunk.size", "1048576");
        self._spark._jsc.hadoopConfiguration().set("fs.gs.outputstream.upload.max.active.requests", "4");

        self._spark.sparkContext.setLogLevel("ERROR")

    def get_data_from_kafka(self):

        # wait for some seconds
        time.sleep(5)

        # Read messages from Kafka
        df = self._spark \
            .read \
            .format("kafka") \
            .option("kafka.bootstrap.servers", KAFKA_URL) \
            .option("kafka.group.id", "elasticsearch_consumer_group_test") \
            .option("subscribe", KAFKA_TOPIC) \
            .option("startingOffsets", "earliest") \
            .load()
        
        # Convert value column from Kafka to string
        df = df.selectExpr("CAST(value AS STRING)")
        logger.info(f"Consume topic: {KAFKA_TOPIC}")
        
        return df
    
    def upload_data_to_elasticsearch(self, batch_df):

        records = batch_df.count()

        # Define the schema to extract specific fields
        schema = StructType() \
                .add("id", StringType()) \
                .add("name", StringType()) \
                .add("username", StringType()) \
                .add("bio", StringType()) \
                .add("location", StringType()) \
                .add("profile_url", StringType()) \
                .add("join_date", StringType()) \
                .add("statuses_count", IntegerType()) \
                .add("friends_count", IntegerType()) \
                .add("followers_count", IntegerType()) \
                .add("favourites_count", IntegerType()) \
                .add("media_count", IntegerType()) \
                .add("protected", StringType()) \
                .add("verified", StringType()) \
                .add("profile_image_url_https", StringType()) \
                .add("profile_banner_url", StringType())
        
        # Parse JSON messages using the adjusted schema
        parsed_df = batch_df.select(from_json(batch_df.value, schema).alias("data")) \
                            .select("data.*")

        # Convert "protected" and "verified" fields to integers (0 or 1)
        parsed_df = parsed_df.withColumn("protected", when(parsed_df["protected"] == "True", 1).otherwise(0)) \
                             .withColumn("verified", when(parsed_df["verified"] == "True", 1).otherwise(0))
        
        # Rename specific fields
        parsed_df = parsed_df \
            .withColumnRenamed("profile_url", "url") \
            .withColumnRenamed("statuses_count", "tweets") \
            .withColumnRenamed("friends_count", "following") \
            .withColumnRenamed("followers_count", "followers") \
            .withColumnRenamed("favourites_count", "likes") \
            .withColumnRenamed("media_count", "media") \
            .withColumnRenamed("profile_image_url_https", "profile_image_url") \
            .withColumnRenamed("profile_banner_url", "background_image")
        
        # Coalesce to a single partition before writing to Parquet
        parsed_df = parsed_df.coalesce(1)

        # Write the data to Elasticsearch
        parsed_df.write \
            .format("org.elasticsearch.spark.sql") \
            .option("es.nodes", ELASTICSEARCH_URL) \
            .option("es.nodes.discovery", "false")\
            .option("es.nodes.wan.only", "true")\
            .option("es.resource", "my_great_test_index") \
            .option("es.net.http.auth.user", ELASTICSEARCH_USER) \
            .option("es.net.http.auth.pass", ELASTICSEARCH_PASSWORD) \
            .option("es.mapping.id", "id") \
            .option("es.write.operation", "upsert")\
            .mode("append") \
            .save()

        logger.info(f"Upload data to Elasticsearch: ({records} records)")

    def consume(self):
        try: 
            df = self.get_data_from_kafka()
            self.upload_data_to_elasticsearch(df)

        except Exception as e:
            logger.error(e)

        finally:
            self._spark.stop()

if __name__ == "__main__":
    consumer = Consumer()
    consumer.consume()