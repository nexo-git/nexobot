"""Glue Job: transforma el JSON enriquecido (raw/conversation_analysis/) a Parquet
particionado por fecha (analytics/conversation_analysis/).

Parámetros del job (Job parameters en consola):
  --SOURCE_PATH   s3://<bucket>/raw/conversation_analysis/
  --TARGET_PATH   s3://<bucket>/analytics/conversation_analysis/
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

args = getResolvedOptions(sys.argv, ["JOB_NAME", "SOURCE_PATH", "TARGET_PATH"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

df = spark.read.json(args["SOURCE_PATH"])

df.write.mode("append").partitionBy("date").parquet(args["TARGET_PATH"])

job.commit()
