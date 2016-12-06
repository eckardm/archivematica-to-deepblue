import os
import shutil
import subprocess
from lxml import etree
import requests

# `\media\sf_DeepBlue` is auto-mounted
staging_dir = os.path.join(os.path.sep, "media", "sf_DeepBlue", "deepblue_saf_staging")
temp_dir = os.path.join(os.path.sep, "media", "sf_DeepBlue", "deepblue_saf_temp")

for root, _, files in os.walk(staging_dir):
    for name in files:

        aip = os.path.join(root, name)

        # make working copy
        shutil.copy(aip, temp_dir)

        aip = os.path.join(temp_dir, name)

        # unarchive aips
        command = [
            "unar",
            "-force-overwrite",
            "-output-directory", temp_dir,
            aip
        ]
        subprocess.call(command)

        os.remove(aip)

        aip_dir = os.path.join(temp_dir, os.path.splitext(aip)[0])

        # get agent
        mets_dir = os.path.join(aip_dir, "data", [name for name in os.listdir(os.path.join(aip_dir, "data")) if name.startswith("METS")][0])

        tree = etree.parse(mets_dir)
        namespaces = {
            "premis": "info:lc/xmlns/premis-v2",
            "dc": "http://purl.org/dc/elements/1.1/"
        }

        user = [agent.xpath("./premis:agentName", namespaces=namespaces)[0].text for agent in tree.xpath("//premis:agent", namespaces=namespaces) if agent.xpath("./premis:agentType", namespaces=namespaces)[0].text == "Archivematica user"][0]
        username = user.split(", ")[0].split('"')[1].split('"')[0]
        first_name = user.split(", ")[1].split('"')[1].split('"')[0]
        last_name = user.split(", ")[2].split('"')[1].split('"')[0]

        # get dcterms
        dcterms_title = tree.xpath(".//dc:title", namespaces=namespaces)[0].text
        dcterms_creator =  tree.xpath(".//dc:creator", namespaces=namespaces)[0].text
        dcterms_date = tree.xpath(".//dc:date", namespaces=namespaces)[0].text
        dcterms_rights = tree.xpath(".//dc:rights", namespaces=namespaces)[0].text

        # get rights statement
        act = tree.xpath(".//premis:act", namespaces=namespaces)[0].text
        restriction = tree.xpath(".//premis:restriction", namespaces=namespaces)[0].text
        start_date = tree.xpath(".//premis:startDate", namespaces=namespaces)[0].text
        end_date = tree.xpath(".//premis:endDate", namespaces=namespaces)[0].text
        rights_granted_note = tree.xpath(".//premis:rightsGrantedNote", namespaces=namespaces)[0].text

        # repackage aips
        objects_dir = os.path.join(aip_dir, "data", "objects", [name for name in os.listdir(os.path.join(aip_dir, "data", "objects")) if name.startswith("digital_object_component")][0])
        objects_zip = os.path.join(aip_dir, "objects.7z")
        command = [
            "7z", "a",  # add
            "-bd",  # disable percentage indicator
            "-t7z",  # type of archive
            "-y",  # assume yes on all queries
            "-m0=bzip2",  # compression method
            "-mtc=on", "-mtm=on", "-mta=on",  # keep timestamps (create, mod, access)
            "-mmt=on",  # multithreaded
            objects_zip,  # destination
            objects_dir,  # source
        ]
        subprocess.call(command)

        shutil.rmtree(objects_dir)

        metadata_zip = os.path.join(aip_dir, "metadata.7z")
        command = [
            "7z", "a",  # add
            "-bd",  # disable percentage indicator
            "-t7z",  # type of archive
            "-y",  # assume yes on all queries
            "-m0=bzip2",  # compression method
            "-mtc=on", "-mtm=on", "-mta=on",  # keep timestamps (create, mod, access)
            "-mmt=on",  # multithreaded
            metadata_zip,  # destination
            aip_dir,  # source
        ]
        subprocess.call(command)
        command = [
            "7z", "d",  # delete
            metadata_zip,  # archive
            "objects.7z",  # file
            "-r"  # recurse
        ]
        subprocess.call(command)

        shutil.rmtree(os.path.join(aip_dir, "data"))
        tags = [
            os.path.join(aip_dir, "bag-info.txt"),
            os.path.join(aip_dir, "bagit.txt"),
            os.path.join(aip_dir, "manifest-sha256.txt"),
            os.path.join(aip_dir, "tagmanifest-md5.txt"),
        ]
        for tag in tags:
            os.remove(tag)

        # create a deepblue item
        dspace_url = "https://dev.deepblue.lib.umich.edu"

        url = dspace_url + "/RESTapi/login"
        body = {"email": "eckardm@umich.edu", "password": "m1deposit"}
        response = requests.post(url, json=body)

        dspace_token = response.text

        collection_id = 1412

        url = dspace_url + "/RESTapi/collections/" + str(collection_id) + "/items"
        headers = {
            "Accept": "application/json",
            "rest-dspace-token": dspace_token
        }
        params = {"expand": "metadata"}
        body = {
            "metadata" : [
                {"key": "dc.title", "value": dcterms_title, "language": None},
                {"key": "dc.contributor.author", "value": dcterms_creator, "language": None},
                {"key": "dc.date.issued", "value": dcterms_date, "language": None},
                {"key": "dc.rights.copyright", "value": dcterms_rights, "language": None}
            ]
        }
        response = requests.post(url, headers=headers, params=params, json=body)

        item_id = response.json().get("id")
        handle = response.json().get("handle")
