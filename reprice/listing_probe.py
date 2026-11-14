"""READ-ONLY / VALIDATION_PREVIEW probe for the AlphaDog Styles Amazon listings.
Nothing is created or published: putListingsItem runs with mode=VALIDATION_PREVIEW. Prints no credentials."""
import json, os, sys
import spapi
HERE = os.path.dirname(os.path.abspath(__file__))
MP = spapi.MARKETPLACE
def main():
    c = spapi.load_creds(HERE)
    seller = c.get("SELLER_ID")
    print("seller id present:", bool(seller))
    for kw in ("t-shirt", "hoodie sweatshirt", "hat cap", "tank top", "polo"):
        try:
            r = spapi.call(c, "GET", "/definitions/2020-09-01/productTypes", params={"marketplaceIds": MP, "keywords": kw})
            print("types for %r:" % kw, [p["name"] for p in r.get("productTypes", [])][:8])
        except spapi.SpError as e:
            print("types for %r: ERROR %s" % (kw, e)); break
    if not seller:
        print("no SELLER_ID: stop"); return
    def attrs(ptype, color, size, title):
        v = lambda x: [{"value": x, "marketplace_id": MP}]
        return {
            "item_name": v(title), "brand": v("AlphaDog Styles"),
            "supplier_declared_has_product_identifier_exemption": v(True),
            "color": v(color), "size": [{"value": size, "marketplace_id": MP}],
            "department": v("unisex"), "age_range_description": v("Adult"),
            "country_of_origin": v("US"), "item_type_keyword": v("t-shirts"),
            "bullet_point": [{"value": "Original dog breed line art", "marketplace_id": MP}],
            "product_description": v("Original dog breed line-art design on a premium blank."),
            "purchasable_offer": [{"marketplace_id": MP, "currency": "USD", "our_price": [{"schedule": [{"value_with_tax": 24.99}]}]}],
            "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT", "quantity": 100}],
        }
    for ptype, title in (("SHIRT", "AlphaDog Styles French Bulldog Line Art Tee"), ("HAT", "AlphaDog Styles French Bulldog Dad Hat")):
        body = {"productType": ptype, "requirements": "LISTING", "attributes": attrs(ptype, "White", "M", title)}
        try:
            r = spapi.call(c, "PUT", "/listings/2021-08-01/items/%s/%s" % (seller, "ALPHADOG-PROBE-" + ptype),
                           params={"marketplaceIds": MP, "issueLocale": "en_US", "mode": "VALIDATION_PREVIEW"}, body=body)
            print(ptype, "status:", r.get("status"))
            for i in r.get("issues", [])[:25]:
                print("  ", i.get("severity"), i.get("code"), (i.get("message") or "")[:220], i.get("attributeNames"))
        except spapi.SpError as e:
            print(ptype, "ERROR", e)
main()
