import xmlschema
import pandas as pd
import numpy as np
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
import os
import re
import base64
from google.cloud import bigquery

from datetime import datetime
import traceback
from logging_config import log_default, log_error


def get_file_dir():
    """
    Returns the directory of the current file.
    """
    return os.path.dirname(os.path.abspath(__file__))

def xml_to_json_projects(xml_file_path):
    """
    Reads an XML file, validates against the schema (handling ContactID error), extracts Project elements, and converts to a list of JSON objects.
    """
    try:
        log_default(log_message="Parsing the XML file",
                    json_payload=json.dumps({"filename": xml_file_path})
        )
        try:
            schema = xmlschema.XMLSchema(f"{get_file_dir()}/xsd_schema/schDataLinkConfV1.4.xsd.xml")
        except Exception as e:
            stack_trace = traceback.format_exc()
            log_error(
                function_name="xml_to_json_projects",
                endpoint="process-xml-files",
                log_message=f"Error loading schema: {str(e)}",
                error_type=type(e).__name__,
                stack_trace=stack_trace,
                json_payload=json.dumps({"filenme": xml_file_path})
            )
            raise f"Error loading schema: {str(e)}"
        
        tree = ET.parse(xml_file_path)  # Parse XML using ElementTree
        root = tree.getroot()
        ET.register_namespace("", 'https://insight.cmdgroup.com/schemas/schDataLinkConfV1.4.xsd')

        #Find and remove invalid ContactID attribute from Company elements
        for company in root.findall('.//{http://insight.cmdgroup.com/schemas/schDataLinkConfV1.4.xsd}Company'):
            if 'ContactID' in company.attrib:
                del company.attrib['ContactID']


        #Convert the corrected XML to a string before passing to schema.to_dict.
        ET.indent(root)
        corrected_xml = ET.tostring(root, encoding="unicode")

        doc = schema.to_dict(corrected_xml, dict_type='list', preserve_root=False)
        doc = {k.replace('ns0:', ''):v for k, v in doc.items()}

        # Extract all projects (handling single project case)
        projects = doc['Project'] if isinstance(doc['Project'], list) else [doc['Project']]

        # Handle potential missing data gracefully (unchanged)
        for project in projects:
            project.setdefault('Connections', [])
            for conn in project.get('Connections', []):
                conn.setdefault('Connection', [])

        return projects
    except xmlschema.XMLSchemaValidationError as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"XML validation error: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise f"XML validation error after correction: {e}"
        
    except FileNotFoundError:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"Error: File not found at {xml_file_path}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise f"Error: File not found at {xml_file_path}"
        
    except ET.ParseError as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"Error parsing XML: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise f"Error parsing XML: {e}"
    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"An unexpected error occurred: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise f"An unexpected error occurred: {e}"

def replace_special_chars_keys(obj):
    """
    Recursively replaces special characters in the keys of a dictionary or elements of a list.
    This function processes dictionaries and lists, replacing special characters in dictionary keys
    with underscores or removing them entirely. It also removes the "ns0:" prefix from keys.
    Args:
        obj (dict or list): The input dictionary or list to process.
    Returns:
        dict or list: A new dictionary or list with special characters removed from keys.
    """
    special_chars = ['!', '"', '$', '(', ')', '*', ',', '.', '/', ';', '?', '@', '[', '\\', ']', '^', '`', '{', '}', '~',' ']
    pattern = re.compile("[" + re.escape("".join(special_chars)) + "]")
    
    
    if isinstance(obj, dict):
        new_dict = {}
        for key, value in obj.items():
            new_key = key.replace("$", "_")  # Replace $ with _
            new_key = new_key.replace("ns0:", "")  # Replace $ with _
            new_key = pattern.sub("", new_key)  # Remove special characters from key
            new_dict[new_key] = replace_special_chars_keys(value) 
        return new_dict
    elif isinstance(obj, list):
        return [replace_special_chars_keys(item) for item in obj]  
    else:
        return obj  


    

def json_to_dataframe(json_data,filename):
    """
    Converts JSON data to a Pandas DataFrame, handling nested dictionaries and arrays.

    Args:
        json_data: A dictionary representing the JSON data.

    Returns:
        A Pandas DataFrame.  Returns None if input is invalid.
    """
    try:
        data = {}
        def flatten_json(json_data, parent_key='', sep='_'):
            items = []
            for k, v in json_data.items():
                new_key = parent_key + sep + k if parent_key else k
                if 'ns0:Details_ns0:Detail' in new_key:
                    detail_types = {}
                    for i in v:
                        if not detail_types.get(i['@DetailType'], None):
                            detail_types[f"Details_Detail_@{i['@DetailType']}"] = []
                            detail_types[f"Details_Detail_@{i['@DetailType']}"].append(i['$'])
                        else:
                            detail_types[f"Details_Detail_@{i['@DetailType']}"].append(i['$'])
                    
                    items.extend(detail_types.items())
                    
                if 'ns0:RSMeansMaterialDivisions_ns0:Division' in new_key:
                    division_types = {}
                    for i in v:
                        if not division_types.get(i['@Description'], None):
                            division_types[f"RSMeansMaterialDivisions_Division_{i['@Description']}"] = []
                            division_types[f"RSMeansMaterialDivisions_Division_{i['@Description']}"].extend(i['ns0:Material'])
                        else:
                            division_types[f"RSMeansMaterialDivisions_Division_{i['@Description']}"].extend(i['ns0:Material'])
                    
                    items.extend(division_types.items())
                            
                            
                elif isinstance(v, dict):
                    items.extend(flatten_json(v, new_key, sep=sep).items())
                
                elif isinstance(v, list):
                    if 'ns0:Companies' in new_key:
                        for v_idx, i in enumerate(v):
                            for c_idx,Company in enumerate(i['ns0:Company']):
                                if Company['ns0:Phones']:
                                    for p_idx,phones in enumerate(Company['ns0:Phones']['ns0:Phone']):
                                        v[v_idx]['ns0:Company'][c_idx]['ns0:Phones']['ns0:Phone'][p_idx]['PhoneNumnber'] = phones['$']
                                        del v[v_idx]['ns0:Company'][c_idx]['ns0:Phones']['ns0:Phone'][p_idx]['$']
                        

                    items.append((new_key, v))
                else:
                    items.append((new_key, v))
            return dict(items)

        flattened_json = flatten_json(json_data)
        flattened_json = {k.replace('ns0:', ''): v for k, v in flattened_json.items()}
        flattened_json = replace_special_chars_keys(flattened_json)  # Remove @ from keys
        
        df = pd.DataFrame([flattened_json])  #Create DataFrame from flattened data

        return df

    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="json_to_dataframe",
            endpoint="process-xml-files",
            log_message=f"Error converting JSON to DataFrame: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filename": filename})
        )   
        raise Exception(f"Error converting JSON to DataFrame: {str(e)}")
        


def process_file(file_path, gcs_client, bucket, settings):
    """
    Downloads an XML file from a Google Cloud Storage bucket, processes it, and converts it to a pandas DataFrame.
    Args:
        file_path (str): The path to the XML file in the Google Cloud Storage bucket.
        b (str): The name of the Google Cloud Storage bucket.
    Returns:
        pandas.DataFrame: A DataFrame containing the processed data from the XML file.
    """

    f_name = f"temp_file_{file_path.split('/')[-1]}"
    gcs_client.download_by_filename(file_path, f_name)
    log_default(log_message=f"Downloaded {file_path}",
                json_payload=json.dumps({"filename": file_path})
    )
    with open(f_name, 'rb') as f:
        xml_file = f.name

        if bucket == settings.GCS_SOURCE_BUCKET or bucket == settings.GCS_BUCKET:
            projects_json = xml_to_json_projects(xml_file)
            project_dfs = [json_to_dataframe(project,file_path) for project in projects_json]
        elif bucket == settings.DODGE_GCS_SOURCE_BUCKET:
            projects_json = dodge_xml_to_json_projects(xml_file)
            project_dfs = [dodge_json_to_dataframe(project,file_path) for project in projects_json]
        else:
            raise Exception(f"Unknown source bucket: {bucket}")
        

        project_df = pd.concat(project_dfs).reset_index(drop = True)

        # Dodge Data Cleaning
        if bucket == settings.DODGE_GCS_SOURCE_BUCKET:
            date_columns = ['DateOfFirstExport', 'DateOfLastExport', 'DateOfCurrentExport', 'FirstIssueDate', 'LastIssueDate', 'ReportDate', 'BidDate', 'TargetStartDate', 'TargetCompletionDate']
            # replacing '//' with NaN for date columns
            project_df[date_columns] = project_df[date_columns].replace('//', np.nan).infer_objects(copy=False)
            # converting date columns to date format
            for col in date_columns:
                project_df[col] = pd.to_datetime(project_df[col], format='%m/%d/%Y')
            # converting integer columns to int format
            int_columns = ['DRNumber', 'VersionNumber', 'StoriesAbove', 'StoriesBelow', 'NoOfBuildings']
            for col in int_columns:
                project_df[col] = project_df[col].astype('Int64')
            
            # Replacing NaN values with None
            project_df = project_df.replace({np.nan: None})

        log_default(log_message=f"Processed {xml_file}",
                json_payload=json.dumps({"filename": xml_file})
        )
        
    return project_df

def push_to_bq(df, big_query_client, TABLE_ID, FILE_PATH, write='WRITE_APPEND'):
    """
    Loads a pandas DataFrame into a BigQuery table.

    Args:
        df (pandas.DataFrame): The DataFrame to load into BigQuery.
        dataset (str): The name of the BigQuery dataset.
        table (str): The name of the BigQuery table.
        write (str, optional): The write disposition for the load job. 
            Defaults to 'WRITE_APPEND'. Other options include 'WRITE_TRUNCATE' and 'WRITE_EMPTY'.

    Returns:
        str: A status code indicating the result of the operation. '200' indicates success.

    Raises:
        google.cloud.exceptions.GoogleCloudError: If the load job fails.
    """
    job_config = bigquery.LoadJobConfig(
        write_disposition = write,
        schema_update_options = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        column_name_character_map = 'V2'
    )
    job = big_query_client.load_from_dataframe(
        table_id=TABLE_ID,
        dataframe=df,
        job_config=job_config
    )
    log_default(log_message=f"Loaded {job.output_rows} rows into {big_query_client._dataset_id}:{TABLE_ID}",
                json_payload=json.dumps({"filename": FILE_PATH})
    )
    return job.output_rows

def ack_receipt():
    return '200'


def dodge_xml_to_json_projects(xml_file_path):
    try:
        log_default(log_message="Parsing the XML file",
                    json_payload=json.dumps({"filename": xml_file_path})
        )
        
        
        tree = ET.parse(xml_file_path)  # Parse XML using ElementTree
        root = tree.getroot()

        for company in root.findall('.//Company'):
            if 'ContactID' in company.attrib:
                del company.attrib['ContactID']

        ET.indent(root)
        def elem_to_dict(elem):
            if not elem.attrib and not list(elem) and (elem.text is None or not elem.text.strip()):
                return None

            d = {}
            
            # Include element attributes
            if elem.attrib:
                d.update(elem.attrib)
            
            # Include child elements
            children = list(elem)
            if children:
                child_dict = {}
                for child in children:
                    child_data = elem_to_dict(child)
                    if child.tag in child_dict:
                        # If tag already exists, convert to list
                        if not isinstance(child_dict[child.tag], list):
                            child_dict[child.tag] = [child_dict[child.tag]]
                        child_dict[child.tag].append(child_data)
                    elif child.tag in 'Company':
                        child_dict[child.tag] = [child_data]
                    else:
                        child_dict[child.tag] = child_data
                d.update(child_dict)
            else:
                # Leaf node
                d = elem.text if elem.text and elem.text.strip() else d

            return d
        

        projects  = {root.tag: elem_to_dict(root)}
        projects =  projects.get('Projects').get('Project')
        return projects
    
    except FileNotFoundError:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="dodge_xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"Error: File not found at {xml_file_path}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise Exception(f"Error: File not found at {xml_file_path}")
        
    except ET.ParseError as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="dodge_xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"Error parsing XML: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise Exception(f"Error parsing XML: {e}")
    except Exception as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="dodge_xml_to_json_projects",
            endpoint="process-xml-files",
            log_message=f"An unexpected error occurred: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filenme": xml_file_path})
        )
        raise Exception(f"An unexpected error occurred: {e}")
    


def dodge_json_to_dataframe(json_data,filename):
    """
    Converts JSON data to a Pandas DataFrame.
    Args:
        json_data: A dictionary representing the JSON data.
    Returns:
        A Pandas DataFrame.  Returns None if input is invalid.
    """
    try:
        
        df = pd.DataFrame([json_data])  #Create DataFrame from flattened data
        return df

    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        stack_trace = traceback.format_exc()
        log_error(
            function_name="dodge_json_to_dataframe",
            endpoint="process-xml-files",
            log_message=f"Error converting JSON to DataFrame: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=stack_trace,
            json_payload=json.dumps({"filename": filename})
        )   
        raise Exception(f"Error converting JSON to DataFrame: {str(e)}")