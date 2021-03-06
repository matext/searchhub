import logging
import os
from flask import render_template, send_from_directory
from flask import request, redirect
from flask import jsonify
from server import app, backend
from werkzeug.security import generate_password_hash, check_password_hash
import werkzeug
import urllib
import json
from os import listdir
from os.path import isfile, join


logging.basicConfig(level=logging.INFO)

LOG = logging.getLogger("views.py")

project_label_map = {}
project_files = [f for f in listdir("./project_config") if isfile(join("./project_config", f)) and f.endswith(".json")]
for file in project_files:
    project = json.load(open(join("./project_config", file)))
    #print ("Loading name: %s" % project["name"] )
    project_label_map[project["name"]] = project["label"]


@app.route('/')
def root():
    return render_template('index.html')

# This route is for back compatibility reasons with the old search hub, although it is not 100% just yet, as we don't handle the passed in paths
@app.route('/p:<path:path>')
def apache(path):
    query = request.args.get("q")
    splits = path.split(",")
    
    # DEPRECATED 
    # fq = ""

    facet_list = [] 
    if splits:
        # DEPRECATED 
        # fq = ",fq:('0':(key:'{!!tag=prj}project_label',tag:prj,transformer:localParams,values:(" #format this into the args
        # i = 0

        for split in splits:
            split = split.strip()
            if split in project_label_map:
                print("in the splits!")
                print(split)

                facet_list.append(project_label_map[split])
                
                # DEPRECATED 
                # if i > 0:
                #     fq += ","
                # fq += "'" + str(i) + "':'" + project_label_map[split] + "'"
                # i += 1
        # fq += ")))"
    # DEPRECATED 
    # print "path: '" + path + "' q: '" + query + "'"
    # args = {"query": "(q:'{0}',rows:10,start:0,wt:json{1})".format(query, fq)}
    
    facet_string = "|".join(facet_list)
    redirect_url = "https://lucidworks.com/resources/searchhub/#hub/" + query + "/1/sortbyrelevancy/facetstring=&facets[project_label]=" + facet_string
    return redirect(redirect_url)

@app.route('/search')
def search():
    return render_template('index.html')

@app.route('/login', methods=["POST"])
def login():
    user_data = request.json

    if (user_data is None) or ("username" not in user_data) or ("password" not in user_data):
        msg = 'Please fill missing fields!'
        return jsonify({"msg": msg, "success": False})

    users = backend.get_user(username=user_data["username"])

    if len(users) == 1:
        user = users[0]
        if check_password_hash(user["password"], user_data["password"]):
            success = True
            msg = "Login success!"
            email = user["email"]
        else:
            success = False
            msg = "Incorrect password!"
    else:
        # user already exists
        success = False
        msg = 'Username does not exists!'


    return jsonify({"msg": msg, "success": success, "email": email})

@app.route('/signup', methods=["POST"])
def signup():
    user_data = request.json

    if (user_data is None) or ("username" not in user_data) or ("email" not in user_data) or \
            ("password" not in user_data) or ("password_confirm" not in user_data):
        msg = 'Please fill missing fields!'
        return jsonify({"msg": msg, "success": False})
    elif len(user_data["password"]) < 6:
        msg = 'Password length must be at least 6'
        return jsonify({"msg": msg, "success": False})
    elif user_data["password"] != user_data["password_confirm"]:
        msg = 'Password does not match!'
        return jsonify({"msg": msg, "success": False})

    user_data["password"] = generate_password_hash(user_data["password"])
    users = backend.get_user(username=user_data["username"], email=user_data["email"])

    if len(users) > 0:
        # user already exists
        success = False
        msg = 'Username or email already exists!'
    else:
        # add new user into collection
        if backend.add_user(user_data):
            success = True
            msg = "Sign up success!"
        else:
            success = False
            msg = "Sign up error!"

    return jsonify({"msg": msg, "success": success})

def iterform(multidict):
    for key in multidict.keys():
        for value in multidict.getlist(key):
            yield (key.encode("utf8"), value.encode("utf8"))

# Route all Signals from Snowplow accordingly
@app.route('/snowplow/<path:path>', methods=["GET"])
def track_event(path):
    # TODO: put in spam prevention
    app_id = request.args.get("aid")
    signal = request.args
    if app_id == "searchHub" and signal:
        coll_id = app.config.get("FUSION_COLLECTION", "lucidfind")
        result = backend.send_signal(coll_id, signal)
    else:
        print "Unable to send signal: app_id: {0}, signal: {1}".format(app_id, signal)
    #Snowplow requires you respond with a 1x1 pixel
    return send_from_directory(os.path.join(app.root_path, 'assets/img/'), 'onebyone.png')

@app.route('/snowplow_post/<path:foo>', methods=["POST"])
def track_post_event(foo):
    # TODO: put in spam prevention
    # NOTE: when POSTing, we can have multiple events per POST
    json_payload = request.get_json()

    data = json_payload["data"]
    for item in data:
        app_id = item["aid"]
        if app_id == "searchHub":
            coll_id = app.config.get("FUSION_COLLECTION", "lucidfind")
            request_headers = {}
            #we need to set a few headers from the client so that the signal shows up properly on the backend
            for h in ["Referer", "User-Agent"]:
                if h in request.headers:
                    request_headers[h] = str(request.headers[h])
            if request.method == "POST" or request.method == "PUT":
                form_data = list(iterform(request.form))
                form_data = urllib.urlencode(form_data)
                request_headers["Content-Length"] = str(len(form_data))
            # The snowplow payload needs to set these to override the underlying python requests setting
            item["ip"] = request.remote_addr
            item["ua"] = request.user_agent
            result = backend.send_signal(coll_id, item, request_headers)
        else:
            print "Unable to send signal: app_id: {0}, signal: {1}".format(app_id, item)
    #Snowplow requires you respond with a 1x1 pixel
    return ""#send_from_directory(os.path.join(app.root_path, 'assets/img/'), 'onebyone.png')

@app.route('/templates/<path:path>')
def send_foundation_template(
        path):  # TODO: we shouldn't need this in production since we shouldn't serve static content from Flask
    return send_from_directory(os.path.join(app.root_path, 'templates'), path)
