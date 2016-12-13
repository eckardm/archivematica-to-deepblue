import requests
from tqdm import *
import json

from auth import archivesspace_url, archivesspace_username, archivesspace_password

def get_eligible_digital_objects():
    url = archivesspace_url + "/users/" + archivesspace_username + "/login?password=" + archivesspace_password
    response = requests.post(url)
    
    archivesspace_token = response.json().get("session")
    
    url = archivesspace_url + "/repositories/2/digital_objects?all_ids=true"
    headers = {"X-ArchivesSpace-Session": archivesspace_token}
    response = requests.get(url, headers=headers)
    
    digital_object_ids = response.json()

    eligible_digital_objects = []
    
    for digital_object_id in tqdm(digital_object_ids):
        url = archivesspace_url + "/repositories/2/digital_objects/" + str(digital_object_id)
        response = requests.get(url, headers=headers)
        
        digital_object = response.json()
        
        if digital_object.get("created_by") == "archivematica" and len(digital_object.get("file_versions")) == 0:
            eligible_digital_objects.append(digital_object)
         
    with open("eligible_digital_objects.json", mode="w") as f:
        json.dump(eligible_digital_objects, f)

if __name__ == "__main__":
    get_eligible_digital_objects()
