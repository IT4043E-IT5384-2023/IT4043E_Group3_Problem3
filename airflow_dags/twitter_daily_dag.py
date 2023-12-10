from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

default_args = {
  "owner": 'airflow',
  "depends_on_past": False,
  "start_date": datetime(2023, 6, 12),
  "retries": 3,
  "retry_delay": timedelta(minutes=10),
}

with DAG(dag_id="twitter_daily_dag",
         default_args=default_args,
         catchup=False,
         schedule="0 0 * * *"
         ) as dag:
    
    producer_task = BashOperator(task_id="producer_task",
                                 bash_command="cd ~/Documents/IT4043E_Group3_Problem3/kafka && python3 twitter_producer.py",
                                 retries=1,
                                 max_active_tis_per_dag=1)

    consumer_task = BashOperator(task_id="consumer_task",
                                 bash_command="cd ~/Documents/IT4043E_Group3_Problem3/kafka && python3 twitter_consumer.py",
                                 retries=1,
                                 max_active_tis_per_dag=1)

    end_task = EmptyOperator(task_id="twitter_daily_dag_done")
    
    producer_task >> consumer_task >> end_task