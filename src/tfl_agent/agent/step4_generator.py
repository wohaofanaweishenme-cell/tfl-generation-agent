from tfl_agent.tools.docx_editor import generate_shell

def generate(spec,selection,out_path):
    return generate_shell(selection['source_path'],spec,out_path,
                          locator_map_path=selection['template'].get('locator_map_path'))
