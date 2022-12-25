import os
import sys
from time import sleep
from instance import terminate_instances, get_instances_ids
from infra_utils import delete_security_group, filters_from_tags, get_infra_info, get_security_groups_ids


def teardown_infra(infra_info_path:str):
    """
    Teardown infra using information saved at infra_info_path.

    @param infra_info_path:str    path of a file containing a pickled InfraInfo object 

    @return                       None
    """
    print("Starting teardown")

    infra_info = get_infra_info(infra_info_path)
    filters = filters_from_tags(infra_info.instances_tags)

    # Get instances dynamically
    if len(infra_info.instances_tags) > 0:
        instances_ids = get_instances_ids(filters)
        
        if len(instances_ids) > 0:
            terminate_instances(instances_ids)
    
        for sec_gp in get_security_groups_ids(filters):
            try:
                delete_security_group(sec_gp)
            except:
                sleep(60)
                delete_security_group(sec_gp)

    print("Teardown complete")


if __name__ == '__main__':
    teardown_infra(os.path.join(sys.path[0], 'infra_info'))
