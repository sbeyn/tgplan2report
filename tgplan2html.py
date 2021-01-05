#!/usr/bin/env python
import argparse, collections, flask, json, logging, os, sys;
from boltons.iterutils import default_enter
from boltons.iterutils import default_visit
from boltons.iterutils import get_path
from boltons.iterutils import remap
from datetime import datetime, timezone
from flask import render_template

global level

# Set name app
app = flask.Flask('tgplan2html')

# Get logging
module = sys.modules['__main__'].__file__
log = logging.getLogger(module)

# Set varaibles
now = datetime.now(timezone.utc).astimezone()
actions = {'create': {'count': 0, 'resources':[]},
           'update': {'count': 0, 'resources':[]},
           'recreate': {'count': 0, 'resources':[]},
           'delete': {'count': 0, 'resources':[]}}

def findkeys(node, kv):
    if isinstance(node, list):
        for i in node:
            for x in findkeys(i, kv):
               yield x
    elif isinstance(node, dict):
        if kv in node:
            yield node[kv]
        for j in node.values():
            for x in findkeys(j, kv):
                yield x

def remerge(*containers, source_map: list = None):

    ret = None

    def remerge_enter(path, key, value):
        new_parent, new_items = default_enter(path, key, value)
        if ret and not path and key is None:
            new_parent = ret
        try:
            # TODO: type check?
            new_parent = get_path(ret, path + (key,))
        except KeyError:
            pass

        if isinstance(value, list):
            # lists are purely additive. See https://github.com/mahmoud/boltons/issues/81
            new_parent.extend(value)
            new_items = []

        return new_parent, new_items

    if source_map is not None:

        def remerge_visit(path, key, value):
            full_path = path + (key,)
            if isinstance(value, list):
                old = source_map.get(full_path)
                if old:
                    old.append(t_name)
                else:
                    source_map[full_path] = [t_name]
            else:
                source_map[full_path] = t_name
            return True

        for t_name, cont in containers:
            ret = remap(cont, enter=remerge_enter, visit=remerge_visit)
    else:
        for cont in containers:
            ret = remap(cont, enter=remerge_enter)


        ret = remap(cont, enter=remerge_enter, visit=remerge_visit)

    return ret

def getAndMergePlanJson(pattern):

    try:
       # Get all files with pattern defined
       path_list = [os.path.join(dirpath,filename) for dirpath, _, filenames in os.walk('.') for filename in filenames if filename.endswith(pattern)]
       log.debug(path_list)

       data = {}
       for jsonfile in path_list:

          with open(jsonfile) as f:
            tmp = [] 
            jtmp = json.load(f)

            jtmp['resource_changes'][0]['terragrunt_path'] = jsonfile.split('/.terragrunt-cache')[0]
            tmp.append(jtmp['resource_changes'][0])
          
            jtmp['resource_changes'] = tmp
 
            data = remerge(("defaults", data), ("overrides", jtmp), source_map={})
       return data

    except Exception as e:
       log.error('{c} - {m}'.format(c = type(e).__name__, m = str(e)))

def createReport(pattern):

    # Set variables
    warning = False

    # Get terragrunt plan merged
    data = getAndMergePlanJson(pattern)
    log.debug(data)

    try:

       # Get resource_changes
       resource_changes = data.get('resource_changes')
       log.debug(resource_changes)

       # Parse resource_changes
       for item in resource_changes:
          before = {}
          after = {}
          action = item['change']['actions']

          if len(action) > 1:
             actions['recreate']['count'] += 1
             action[0] = 'recreate'
          elif action[0] == 'create':
             actions['create']['count'] += 1
          elif action[0] == 'update':
             actions['update']['count'] += 1
          elif action[0] == 'delete':
             actions['delete']['count'] += 1
          else:
             actions['read']['count'] += 1

          if item['change']['before']:
             for k, v in item['change']['before'].items():
                 before[k] = v

          if item['change']['after_unknown']:
             for k, v in item['change']['after_unknown'].items():
                 after[k] = v

          if item['change']['after']:
             for k, v in item['change']['after'].items():
                 after[k] = v
       
          actions[action[0]]['resources'].append({'type': item['type'], 'path': item['terragrunt_path'], 'mode': item['mode'], 'before': before, 'after': after})

       log.debug(actions)
       
       # Set render html report
       rendered = render_template('report.html', reporttime=now, data=actions)
       log.debug(rendered)

       # Write file report.html
       f = open("report.html", "w")
       f.write(rendered)
       f.close()
    
       log.debug('report.html generated to ' + str(now))

    except Exception as e:
       log.error('{c} - {m}'.format(c = type(e).__name__, m = str(e)))

if __name__ == '__main__':
    with app.app_context():

       parser = argparse.ArgumentParser()
       parser.add_argument("jsonplan", type=str, nargs='?', const=1, default='plan.out.json',
                           help="terraform plan to json format (default: plan.out.json)")
       parser.add_argument("-v", "--verbose", action="store_true",
                           help="increase output verbosity")
       args = parser.parse_args()
       if args.verbose:
           level=logging.DEBUG
       else:
           level=logging.ERROR

       # Set logging config   
       logging.basicConfig(stream=sys.stderr, level=level, format='(%(levelname)s): %(message)s')

       # Create report html from terragrunt plan-all
       createReport(args.jsonplan)
