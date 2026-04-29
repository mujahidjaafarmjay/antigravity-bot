import json

old_json = """{"type": "service_account", "project_id": "antigravity-bot-494313", "private_key_id": "11a84eb29b8061dd10280850000329759649c8fd", "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC1Ry2/5UNlycLA\\nXjNwZN5OVdXD8BsHa1XmIWPEc9/I2COitK3z/7l5al1qBEaWwUPfJzcDwCAlmZUv\\n8bo/+tMK7BqUHA08JC18D8g4f7oZouFjx8VsJMD2Uhw64rZNlxAGvW9avyiIcoia\\noxEzcHvC84YFNU3vfv/OqDIwJGWRwBmClZfEROpRQgNYgvwCZfe75oP5/LEJZiAI\\nunXsshK1i0rPuGgWhlLd3QuQZNCiEzV6NxoWWt8DiOPY6YZL1LixoCyGpXpxdllL\\nr9YR/L+Z9mX1Svfsq2pIs4AHgevH2ggl8rbgytdTDwA5cTaUC2lrGassR8vK7g8O\\nF9GIhgnrAgMBAAECggEAFg/bmYcldLXhZdgRGpSsGYyIv5fxMi31/lQB+F7B1Ye4\\njoy+vvtYb1ZqmAR9MsvCnt3+7A3t26WdaoBY0oCMPsANXAkt8yvT/U1OaNHirEwO\\ncj5V4Jt4gIHtvZzp4veHk8pqSvkIzdJina9K4J/H8CoDHY8nNQaXy2bc9M75LYun\\nCDlujzkD480op6VWzS5eU6SVu4Qd2RJz4JBNAJZP1oLfPX7hcBA7ZgozIt8own0b\\nM4DhcAe0WC6S2vnlpzyp5/s8jeuX41BCoXWJzI8/cxRNfEl0fXJN7oQGpRMkalLJ\\nEWlQzr45K3Ea+X+cR4IKNg3JuVz5XzaVYsUQX8MfwQKBgQDkg0WlU4nvSJUA7z95\\nVNuwwb9KP/3z11hJvb+CJmd/u/SLS1mTRp4PxGxq1e+/EnDLKzX+nFjJQ+QLOftt\\nRu+XDwDI+Jqmlrdm3jwlYtAivONg473yFpVU4cquAsfVMJbUP7ixtBVUKt1aAUh2\\n9VTwa91Q9Few2i2OfT1agEaM3wKBgQDLFWEwjslChKmHQ5U2l841c8TWnCZ+okDG\\niHiXTwsjYcApCbHNZlIydvs+/ivFwszbRJo9mQpq///m80FFZ2ukcGMot6Jkc4T7\\nbnbgkrVfg1UAxeIy9uBU0ceNDOAYLX9NmF3M1chFwW/0P7NeuMBlGJ0q9GjHAKobW\\nilsBiIVYdQKBgDA2LgSCipCMjLtkvsyXhb5WMki1FZxTq9HrEbOg7Kc7fY3B+QUk\\nmgaTl5g2yN1UQ63p0PuF+wmDpGJl+lEE7Vm+lZjRMrfBBrLSYng0z9r0ZTi09AdW\\nkm0VMlDiT00AcmIXi50adIGMhaUOrj5C5ofPCiOhWbr7XS855y7n73qbAoGANAGq\\nnPPD6IvumhwdhxiDDz8xZkAgv4cvjWf/ccglMw9iVWANL2uHmzLLDouqi/9h1LkR\\nwrqBZ3tdfjhHO83LTBYX3qKALLdEk+cE9CeL/KC/yqtzZ1ZP39lWeK1NJvaIPXm9\\n4C7w9lQoTz640PuyTTvcsOaXXP3HAAP4YEEk3M0CgYEAvZDJwVjZmmsthVJMKsoY\\nX9ixmEfDYtJEXSk97E6dxisousGiKmTf0m8K5MyITZHlCSYcOPDNRYPxH4m6T+fE\\ne0g5S9U6iTNddP8Lv3+4sHFD6MNIM3VFFzaKiX2uEac8rVNDjvBas47MIHnSQ8/f\\nYSS8ThnL6ALZZ67xFSLgadM=\\n-----END PRIVATE KEY-----\\n", "client_email": "trading-bot@antigravity-bot-494313.iam.gserviceaccount.com"}"""

new_json = """{
  "type": "service_account",
  "project_id": "antigravity-bot-494313",
  "private_key_id": "11a84eb29b8061dd10280850000329759649c8fd",
  "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC1Ry2/5UNlycLA\\nXjNwZN5OVdXD8BsHa1XmIWPEc9/I2COitK3z/7l5al1qBEaWwUPfJzcDwCAlmZUv\\n8bo/+tMK7BqUHA08JC18D8g4f7oZouFjx8VsJMD2Uhw64rZNlxAGvW9avyiIcoia\\noxEzcHvC84YFNU3vfv/OqDIwJGWRwBmClZfEROpRQgNYgvwCZfe75oP5/LEJZiAI\\nunXsshK1i0rPuGgWhlLd3QuQZNCiEzV6NxoWWt8DiOPY6YZL1LixoCyGpXpxdllL\\nr9YR/L+Z9mX1Svfsq2pIs4AHgevH2ggl8rbgytdTDwA5cTaUC2lrGassR8vK7g8O\\nF9GIhgnrAgMBAAECggEAFg/bmYcldLXhZdgRGpSsGYyIv5fxMi31/lQB+F7B1Ye4\\njoy+vvtYb1ZqmAR9MsvCnt3+7A3t26WdaoBY0oCMPsANXAkt8yvT/U1OaNHirEwO\\ncj5V4Jt4gIHtvZzp4veHk8pqSvkIzdJina9K4J/H8CoDHY8nNQaXy2bc9M75LYun\\nCDlujzkD480op6VWzS5eU6SVu4Qd2RJz4JBNAJZP1oLfPX7hcBA7ZgozIt8own0b\\nM4DhcAe0WC6S2vnlpzyp5/s8jeuX41BCoXWJzI8/cxRNfEl0fXJN7oQGpRMkalLJ\\nEWlQzr45K3Ea+X+cR4IKNg3JuVz5XzaVYsUQX8MfwQKBgQDkg0WlU4nvSJUA7z95\\nVNuwwb9KP/3z11hJvb+CJmd/u/SLS1mTRp4PxGxq1e+/EnDLKzX+nFjJQ+QLOftt\\nRu+XDwDI+Jqmlrdm3jwlYtAivONg473yFpVU4cquAsfVMJbUP7ixtBVUKt1aAUh2\\n9VTwa91Q9Few2i2OfT1agEaM3wKBgQDLFWEwjslChKmHQ5U2l841c8TWnCZ+okDG\\niHiXTwsjYcApCbHNZlIydvs+/ivFwszbRJo9mQpq///m80FFZ2ukcGMot6Jkc4T7\\nnbgkrVfg1UAxeIy9uBU0ceNDOAYLX9NmF3M1chFwW/0P7NeuMBlGJ0q9GjHAKobW\\nilsBiIVYdQKBgDA2LgSCipCMjLtkvsyXhb5WMki1FZxTq9HrEbOg7Kc7fY3B+QUk\\nmgaTl5g2yN1UQ63p0PuF+wmDpGJl+lEE7Vm+lZjRMrfBBrLSYng0z9r0ZTi09AdW\\nkm0VMlDiT00AcmIXi50adIGMhaUOrj5C5ofPCiOhWbr7XS855y7n73qbAoGANAGq\\nnPPD6IvumhwdhxiDDz8xZkAgv4cvjWf/ccglMw9iVWANL2uHmzLLDouqi/9h1LkR\\nwrqBZ3tdfjhHO83LTBYX3qKALLdEk+cE9CeL/KC/yqtzZ1ZP39lWeK1NJvaIPXm9\\n4C7w9lQoTz640PuyTTvcsOaXXP3HAAP4YEEk3M0CgYEAvZDJwVjZmmsthVJMKsoY\\nX9ixmEfDYtJEXSk97E6dxisousGiKmTf0m8K5MyITZHlCSYcOPDNRYPxH4m6T+fE\\ne0g5S9U6iTNddP8Lv3+4sHFD6MNIM3VFFzaKiX2uEac8rVNDjvBas47MIHnSQ8/f\\nYSS8ThnL6ALZZ67xFSLgadM=\\n-----END PRIVATE KEY-----\\n",
  "client_email": "trading-bot@antigravity-bot-494313.iam.gserviceaccount.com"}"""

d1 = json.loads(old_json)
d2 = json.loads(new_json)

p1 = d1["private_key"].replace("\\n", "\n").replace("-----BEGIN PRIVATE KEY-----\n", "").replace("\n-----END PRIVATE KEY-----\n", "").replace("\n", "")
p2 = d2["private_key"].replace("\\n", "\n").replace("-----BEGIN PRIVATE KEY-----\n", "").replace("\n-----END PRIVATE KEY-----\n", "").replace("\n", "")

print("Old:", len(p1))
print("New:", len(p2))

for i in range(len(p2)):
    if p1[i] != p2[i]:
        print(f"Difference at char {i}: '{p1[i]}' vs '{p2[i]}'")
        print(f"Context old: {p1[i-10:i+10]}")
        print(f"Context new: {p2[i-10:i+10]}")
        break

if len(p1) > len(p2):
    print("Old key has extra character:", repr(p1[len(p2):]))
