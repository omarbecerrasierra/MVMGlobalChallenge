
import pandas as pd
import os
import random
from datetime import datetime
from fastapi import FastAPI
from mangum import Mangum
from mysql.connector import connect
import boto3
import json


def get_secret():
    secret_name = os.environ['DB_PASSWORD_ARN']
    region_name = "us-east-2"  # Cambia esto a tu región

    # Crea un cliente de Secrets Manager
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    
    # Suponiendo que tu secreto es una cadena JSON, esto lo parsea y retorna el objeto
    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
        return json.loads(secret)
    
    else:
        raise Exception("Secret not found")

secret = get_secret()
# Database connection details
host = secret['host']
dbname = secret['dbname']
user = secret['username']
password = secret['password']
port = secret['port']


def create_model():
    create_departments_table = """
    CREATE TABLE IF NOT EXISTS departments (
        department_id INTEGER PRIMARY KEY,
        department_name VARCHAR(255) NOT NULL
    );
    """

    create_job_titles_table = """
    CREATE TABLE IF NOT EXISTS job_titles (
        job_id INTEGER PRIMARY KEY,
        job_title VARCHAR(255) NOT NULL
    );
    """

    create_employees_table = """
    CREATE TABLE IF NOT EXISTS employees (
        employee_id INTEGER PRIMARY KEY,
        employee_name VARCHAR(255) NOT NULL,
        department_id INTEGER,
        job_id INTEGER,
        hire_date DATE NOT NULL,
        FOREIGN KEY (department_id) REFERENCES departments(department_id),
        FOREIGN KEY (job_id) REFERENCES job_titles(job_id)
    );
    """
    return create_departments_table, create_job_titles_table, create_employees_table



def create_data_rows(num_employees: int = 100):
    path_lambda = "/tmp"
    # Departamentos Data
    departments_data = {
        "department_id":  [1, 2, 3, 4, 5],
        "department_name": ["IT", "Human Resources", "Finance", "Marketing", "Sales"]
    }

    # Puestos de trabajo Data
    job_titles_data = {
        "job_id": [101, 102, 103, 104, 105],
        "job_title": ["Software Developer", "HR Manager", "Financial Analyst", "Marketing Specialist", "Sales Representative"]
    }

    # Empleados Data
    employees_data = {
        "employee_id": [i for i in range(num_employees)],
        "employee_name": [f"Employee {i}" for i in range(num_employees)],
        "department_id": random.choices([1, 2, 3, 4, 5], k=num_employees),
        "job_id": random.choices([101, 102, 103, 104, 105], k=num_employees),
        "hire_date": [datetime(2021, random.randint(1, 12), random.randint(1, 28)).strftime("%Y-%m-%d") for _ in range(num_employees)]
    }

    # Convertir a DataFrame
    departments_df = pd.DataFrame(departments_data)
    job_titles_df = pd.DataFrame(job_titles_data)
    employees_df = pd.DataFrame(employees_data)

    employees_df.to_parquet(f"{path_lambda}/employees.parquet", index=False)
    departments_df.to_parquet(f"{path_lambda}/departments.parquet", index=False)
    job_titles_df.to_parquet(f"{path_lambda}/job_titles.parquet", index=False)

def load_data():


    # Establish connection
    conn = connect(host=host, user=user, password=password, database=dbname, port=port)
    cur = conn.cursor()

    # Create tables
    create_departments_table, create_job_titles_table, create_employees_table = create_model()
    cur.execute(create_departments_table)
    cur.execute(create_job_titles_table)
    cur.execute(create_employees_table)

    conn.commit()

    # Assuming /tmp is where you've stored your parquet files
    employees_df = pd.read_parquet('/tmp/employees.parquet')
    departments_df = pd.read_parquet('/tmp/departments.parquet')
    job_titles_df = pd.read_parquet('/tmp/job_titles.parquet')

    # Here you can insert the data into your PostgreSQL database
    # Insert departments data
    for _, row in departments_df.iterrows():
        cur.execute("INSERT INTO departments (department_id, department_name) VALUES (%s, %s)", (row['department_id'], row['department_name']))
    
    # Insert job titles data
    for _, row in job_titles_df.iterrows():
        cur.execute("INSERT INTO job_titles (job_id, job_title) VALUES (%s, %s)", (row['job_id'], row['job_title']))
    
    # Insert employees data
    for _, row in employees_df.iterrows():
        cur.execute("INSERT INTO employees (employee_id, employee_name, department_id, job_id, hire_date) VALUES (%s, %s, %s, %s, %s)", (row['employee_id'], row['employee_name'], row['department_id'], row['job_id'], row['hire_date']))
    
    conn.commit()

    # Close connections
    cur.close()
    conn.close()

def create_view_table ():
    create_view = """
            CREATE OR REPLACE VIEW employee_summary AS
            SELECT
                e.employee_name AS "Employee Name",
                jt.job_title AS "Job Title",
                d.department_name AS "Department",
                e.hire_date AS "Hire Date"
            FROM
                employees e
                JOIN departments d ON e.department_id = d.department_id
                JOIN job_titles jt ON e.job_id = jt.job_id
            ORDER BY
                d.department_name, e.hire_date;
    """
    # create view postgress
    conn = connect(host=host, user=user, password=password, database=dbname, port=port)
    cur = conn.cursor()
    cur.execute(create_view)
    conn.commit()
    cur.close()
    conn.close()

app = FastAPI()
handler = Mangum(app)

@app.post("/create_data")
def create_data():
    create_data_rows()
    load_data()
    return {"status": "success", "message": "Data loaded successfully"}

@app.post("/create_view")
def create_view():
    create_view_table()
    return {"status": "success", "message": "View created successfully"}

@app.get("/view_summary")
def view_summary():
    conn = connect(host=host, user=user, password=password, database=dbname, port=port)
    cur = conn.cursor()
    cur.execute("SELECT * FROM employee_summary;")
    data = cur.fetchall()
    cur.close()
    conn.close()
    # to dataframe
    df = pd.DataFrame(data, columns=["Employee Name", "Job Title", "Department", "Hire Date"])
    return {"status": "success", "data": df.to_dict(orient="records")}


app.get("/")
def read_root():
    return {"Hello": "World"}