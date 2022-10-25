def get_userinfo_from_request_json():
    """
    :return: user_data
    user_data is
    [username, domain]
    """

    def get_target_value(a={}, index_dict=[]):
        for i in index_dict:
            if a.get(i):
                if len(index_dict) > 1:
                    index_dict.pop(0)
                    return get_target_value(a.get(i), index_dict)
                elif len(index_dict) == 1:
                    return a.get(i)
                else:
                    return None
            else:
                return None
    request_json = {'auth': {'scope': {'project': {'id': '840055620f8446d2b298ea01fc6d8997'}}, 'identity': {'password': {'user': {'domain': {'name': 'Default'}, 'password': 'l141tRm8K9CmFX4C', 'name': 'admin'}}, 'methods': ['password']}}}
    user_index = ['auth', 'identity', 'password', 'user', 'name']
    domain_index = ['auth', 'identity', 'password', 'user', 'domain', 'name']
    user_data = (get_target_value(request_json, user_index),
                 get_target_value(request_json, domain_index))
    return user_data

import jinja2

if __name__ == '__main__':
    exit(get_userinfo_from_request_json())
