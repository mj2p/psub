from typing import Dict, List, Union

import rich_click as click

from client.psub import PsubClient

pass_pSub = click.make_pass_decorator(PsubClient)


def get_as_list(list_inst: Union[List, Dict]) -> List[Dict]:
    if isinstance(list_inst, dict):
        list_inst = [list_inst]
    return list_inst


def is_random(psub_obj: PsubClient, randomise: bool) -> str:
    if (
        randomise
        and not psub_obj.invert_random
        or not randomise
        and psub_obj.invert_random
    ):
        return "(random)"

    return ""
