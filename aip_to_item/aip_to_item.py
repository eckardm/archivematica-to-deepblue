import os
import shutil
import subprocess
from lxml import etree

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
