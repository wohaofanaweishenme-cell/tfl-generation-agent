import re
from pathlib import Path
from tfl_agent.tools.io_utils import read_json
from tfl_agent.tools.pdf_parser import parse_sap

# When no Content List is supplied, an explicit requested target is safest.
# Auto-identification is deliberately bounded, never claims full study coverage.
NUMBERED_TABLE = re.compile(r'(?i)\bTable\s+(\d+(?:\.\d+){1,4})\s*[:–—-]?\s*([^\n]{8,120})')

def parse_inputs(sap_path,content_list_path=None,tfl_id=None,title=None):
    sap=parse_sap(sap_path)
    source='explicit_target'; inventory=[]
    if content_list_path:
        data=read_json(content_list_path)
        entries=data['entries'] if isinstance(data,dict) else data
        for i,x in enumerate(entries):
            name=x.get('title') or x.get('tfl_title')
            ident=x.get('tfl_id') or x.get('id')
            kind=x.get('output_type') or x.get('tfl_type') or 'table'
            if not ident or not name: raise ValueError(f'Invalid Content List entry {i+1}: missing id/title')
            inventory.append({'tfl_id':str(ident),'title':str(name),'output_type':kind.lower(),
                              'order':i+1,'identification_source':'content_list'})
        source='content_list'
        if tfl_id:
            inventory=[x for x in inventory if x['tfl_id']==str(tfl_id)]
            if not inventory:raise ValueError('Requested --tfl-id was not found in Content List')
            if title and inventory[0]['title']!=title:
                raise ValueError('Provided --title disagrees with Content List title')
    elif tfl_id and title:
        inventory=[{'tfl_id':tfl_id,'title':title,'output_type':'table','order':1,
                    'identification_source':'user_target'}]
    elif tfl_id or title:
        raise ValueError('--tfl-id and --title must both be supplied when no Content List is given')
    else:
        # Limited heuristic only, not an assertion that all TFLs were identified.
        seen=set()
        for b in sap['blocks']:
            for match in NUMBERED_TABLE.finditer(b['text']):
                ident=match.group(1); name=match.group(2).strip(' .;:')
                if ident not in seen and name:
                    seen.add(ident)
                    inventory.append({'tfl_id':ident,'title':name,'output_type':'table',
                                      'order':len(inventory)+1,'identification_source':'sap_heuristic_unverified'})
        source='sap_heuristic_unverified'
    if not inventory:
        raise ValueError('No TFL target identified. Supply a Content List JSON or --tfl-id plus --title.')
    ids=[x['tfl_id'] for x in inventory]
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate tfl_id in inventory')
    return sap,inventory,source
