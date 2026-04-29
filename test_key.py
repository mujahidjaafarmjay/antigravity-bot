import json
import base64

creds_json = """{"type": "service_account", "project_id": "antigravity-bot-494313", "private_key_id": "11a84eb29b8061dd10280850000329759649c8fd", "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC1Ry2/5UNlycLA\\nXjNwZN5OVdXD8BsHa1XmIWPEc9/I2COitK3z/7l5al1qBEaWwUPfJzcDwCAlmZUv\\n8bo/+tMK7BqUHA08JC18D8g4f7oZouFjx8VsJMD2Uhw64rZNlxAGvW9avyiIcoia\\noxEzcHvC84YFNU3vfv/OqDIwJGWRwBmClZfEROpRQgNYgvwCZfe75oP5/LEJZiAI\\nunXsshK1i0rPuGgWhlLd3QuQZNCiEzV6NxoWWt8DiOPY6YZL1LixoCyGpXpxdllL\\nr9YR/L+Z9mX1Svfsq2pIs4AHgevH2ggl8rbgytdTDwA5cTaUC2lrGassR8vK7g8O\\nF9GIhgnrAgMBAAECggEAFg/bmYcldLXhZdgRGpSsGYyIv5fxMi31/lQB+F7B1Ye4\\njoy+vvtYb1ZqmAR9MsvCnt3+7A3t26WdaoBY0oCMPsANXAkt8yvT/U1OaNHirEwO\\ncj5V4Jt4gIHtvZzp4veHk8pqSvkIzdJina9K4J/H8CoDHY8nNQaXy2bc9M75LYun\\nCDlujzkD480op6VWzS5eU6SVu4Qd2RJz4JBNAJZP1oLfPX7hcBA7ZgozIt8own0b\\nM4DhcAe0WC6S2vnlpzyp5/s8jeuX41BCoXWJzI8/cxRNfEl0fXJN7oQGpRMkalLJ\\nEWlQzr45K3Ea+X+cR4IKNg3JuVz5XzaVYsUQX8MfwQKBgQDkg0WlU4nvSJUA7z95\\nVNuwwb9KP/3z11hJvb+CJmd/u/SLS1mTRp4PxGxq1e+/EnDLKzX+nFjJQ+QLOftt\\nRu+XDwDI+Jqmlrdm3jwlYtAivONg473yFpVU4cquAsfVMJbUP7ixtBVUKt1aAUh2\\n9VTwa91Q9Few2i2OfT1agEaM3wKBgQDLFWEwjslChKmHQ5U2l841c8TWnCZ+okDG\\niHiXTwsjYcApCbHNZlIydvs+/ivFwszbRJo9mQpq///m80FFZ2ukcGMot6Jkc4T7\\nbnbgkrVfg1UAxeIy9uBU0ceNDOAYLX9NmF3M1chFwW/0P7NeuMBlGJ0q9GjHAKobW\\nilsBiIVYdQKBgDA2LgSCipCMjLtkvsyXhb5WMki1FZxTq9HrEbOg7Kc7fY3B+QUk\\nmgaTl5g2yN1UQ63p0PuF+wmDpGJl+lEE7Vm+lZjRMrfBBrLSYng0z9r0ZTi09AdW\\nkm0VMlDiT00AcmIXi50adIGMhaUOrj5C5ofPCiOhWbr7XS855y7n73qbAoGANAGq\\nnPPD6IvumhwdhxiDDz8xZkAgv4cvjWf/ccglMw9iVWANL2uHmzLLDouqi/9h1LkR\\nwrqBZ3tdfjhHO83LTBYX3qKALLdEk+cE9CeL/KC/yqtzZ1ZP39lWeK1NJvaIPXm9\\n4C7w9lQoTz640PuyTTvcsOaXXP3HAAP4YEEk3M0CgYEAvZDJwVjZmmsthVJMKsoY\\nX9ixmEfDYtJEXSk97E6dxisousGiKmTf0m8K5MyITZHlCSYcOPDNRYPxH4m6T+fE\\ne0g5S9U6iTNddP8Lv3+4sHFD6MNIM3VFFzaKiX2uEac8rVNDjvBas47MIHnSQ8/f\\nYSS8ThnL6ALZZ67xFSLgadM=\\n-----END PRIVATE KEY-----\\n", "client_email": "trading-bot@antigravity-bot-494313.iam.gserviceaccount.com", "client_id": "104489759823716700623", "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token", "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs", "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/trading-bot%40antigravity-bot-494313.iam.gserviceaccount.com", "universe_domain": "googleapis.com"}"""

creds_dict = json.loads(creds_json)
pk = creds_dict["private_key"]
pk = pk.replace("\\n", "\n")

print(repr(pk[-50:]))

b64_payload = pk.replace("-----BEGIN PRIVATE KEY-----\n", "").replace("\n-----END PRIVATE KEY-----\n", "").replace("\n", "")

print("Length of b64:", len(b64_payload))
print("Is valid base64?", len(b64_payload) % 4 == 0)

try:
    decoded = base64.b64decode(b64_payload, validate=True)
    print("Decoded length:", len(decoded))
except Exception as e:
    print("Base64 error:", e)

