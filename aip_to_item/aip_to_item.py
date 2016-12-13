import os
import shutil
import subprocess
from lxml import etree
import requests
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from slacker import Slacker

import get_eligible_digital_objects

def aip_to_item():
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

            from auth import dspace_email, dspace_password

            url = dspace_url + "/RESTapi/login"
            body = {"email": dspace_email, "password": dspace_password}
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
            item_handle = response.json().get("handle")

            # create metadata bitstream on deepblue item
            url = dspace_url + "/RESTapi/items/" + str(item_id) + "/bitstreams"
            with open(metadata_zip, mode="r") as f:
                content = f.read()
            response = requests.post(url, headers=headers, data=content)

            bitstream_id = response.json().get("id")

            url = dspace_url + "/RESTapi/bitstreams/" + str(bitstream_id)
            response = requests.get(url)

            bitstream = response.json()

            params = {"expand": "policies"}
            body = bitstream
            body["name"] = "metadata.7z"
            body["description"] = "Administrative information. Access restricted to Bentley staff."
            body["policies"] = [{"action":"READ", "groupId": "1335", "rpType": "TYPE_CUSTOM"}]  # BentleyStaff
            response = requests.put(url, headers=headers, params=params, json=body)

            # create objects bitstream on deepblue item
            url = dspace_url + "/RESTapi/items/" + str(item_id) + "/bitstreams"
            with open(objects_zip, mode="r") as f:
                content = f.read()
            response = requests.post(url, headers=headers, data=content)

            bitstream_id = response.json().get("id")

            url = dspace_url + "/RESTapi/bitstreams/" + str(bitstream_id)
            response = requests.get(url)

            bitstream = response.json()

            body = bitstream
            body["name"] = "objects.7z"

            if rights_granted_note.startswith("Reading-Room Only"):
                body["description"] = "Archival materials. Access restricted to Bentley Reading Room."
                body["policies"] = [{"action":"READ", "groupId": "1002", "rpType": "TYPE_CUSTOM"}]  # Bentley Only Users
            elif rights_granted_note.startswith("UM Only"):
                body["description"] = "Archival materials. Access restricted to UM users."
                body["policies"] = [{"action":"READ", "groupId": "80", "rpType": "TYPE_CUSTOM"}]  # UM Users
            elif rights_granted_note.startswith("Streaming Only"):
                body["description"] = "Archival materials. Access restricted to Bentley staff."
                body["policies"] = [{"action":"READ", "groupId": "1335", "rpType": "TYPE_CUSTOM"}]  # BentleyStaff
            elif restriction == "Disallow":
                body["description"] = "Archival materials. Access restricted to Bentley staff."
                body["policies"] = [{"action":"READ", "groupId": "1335", "rpType": "TYPE_CUSTOM"}]  # BentleyStaff

                driver = webdriver.Firefox(executable_path="/home/eckardm/archivematica-to-deepblue/aip_to_item/geckodriver")

                driver.get(dspace_url + "/handle/" + item_handle)

                wait = WebDriverWait(driver, 10)
                wait.until(EC.title_is(dcterms_title))
                driver.find_element_by_link_text("Login").click()

                from auth import umich_uniqname, umich_password

                wait.until(EC.title_is("U-M Weblogin"))
                driver.find_element_by_id("login").send_keys(umich_uniqname)
                driver.find_element_by_id("password").send_keys(umich_password)
                driver.find_element_by_id("loginSubmit").click()

                wait.until(EC.title_is("Deep Blue: Deposits & Workflow"))
                driver.get(dspace_url + "/handle/" + item_handle)

                wait.until(EC.title_is(dcterms_title))
                driver.find_element_by_link_text("Edit this item").click()

                wait.until(EC.title_is("Deep Blue: Item Status"))
                try:
                    driver.find_element_by_id("aspect_administrative_item_EditItemStatusForm_field_submit_authorization").click()

                    wait.until(EC.title_is("Deep Blue: Edit Item's Policies"))
                except:
                    print "retrying..."
                    driver.find_element_by_id("aspect_administrative_item_EditItemStatusForm_field_submit_authorization").click()

                    wait.until(EC.title_is("Deep Blue: Edit Item's Policies"))
                try:
                    driver.find_element_by_css_selector("tr.ds-table-row:nth-child(3) > td:nth-child(2) > a:nth-child(1)").click()

                    wait.until(EC.title_is("Deep Blue: Edit Policy"))
                except:
                    print "retrying..."
                    driver.find_element_by_css_selector("tr.ds-table-row:nth-child(3) > td:nth-child(2) > a:nth-child(1)").click()

                    wait.until(EC.title_is("Deep Blue: Edit Policy"))
                [option for option in driver.find_elements_by_tag_name("option") if option.text == "BentleyStaff"][0].click()  # BentleyStaff
                driver.find_element_by_id("aspect_administrative_authorization_EditPolicyForm_field_submit_save").click()

                wait.until(EC.title_is("Deep Blue: Edit Item's Policies"))
                try:
                    driver.find_element_by_id("aspect_administrative_authorization_EditItemPolicies_field_submit_return").click()

                    wait.until(EC.title_is("Deep Blue: Item Status"))
                except:
                    print "retrying..."
                    driver.find_element_by_id("aspect_administrative_authorization_EditItemPolicies_field_submit_return").click()

                    wait.until(EC.title_is("Deep Blue: Item Status"))
                try:
                    driver.find_element_by_id("aspect_administrative_item_EditItemStatusForm_field_submit_return").click()

                    wait.until(EC.title_is(dcterms_title))
                except:
                    print "retrying..."
                    driver.find_element_by_id("aspect_administrative_item_EditItemStatusForm_field_submit_return").click()

                    wait.until(EC.title_is(dcterms_title))

                driver.quit()

            response = requests.put(url, headers=headers, params=params, json=body)

            # notify archivist
            from auth import slack_token

            slack = Slacker(slack_token)

            if username == "dproud":
                slack.chat.post_message(
                    "#digital-processing",
                    str("@" + username + ' "' + dcterms_title + '" has been deposited to DeepBlue: https://dev.deepblue.lib.umich.edu/handle/' + item_handle + " :cavaliers: :partyparrot:"),
                )
            else:
                slack.chat.post_message(
                    "#digital-processing",
                    str("@" + username + ' "' + dcterms_title + '" has been deposited to DeepBlue: https://dev.deepblue.lib.umich.edu/handle/' + item_handle + " :bananadance: :partyparrot:"),
                )

if __name__ == "__main__":
    get_eligible_digital_objects.get_eligible_digital_objects()
    aip_to_item()
