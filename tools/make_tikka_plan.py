"""Writes sample_output/tikka_n_kabab.plan.json: the OFFLINE fallback plan for Tikka N Kabab,
written only from the real facts the team collected (name, address, phone, hours, 4.2 rating,
5 menu items with prices). Unknowns stay as [placeholders]. Run: python tools/make_tikka_plan.py"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Tikka N Kabab"
ADDR = "7859 McCallum Blvd Ste 106, Dallas, TX 75252"
MENU = "Chicken Samosa (2 pc) $2.99, Veg Samosa (2 pc) $3.99, Onion Bhaji (pakoda) $5.99, Dal Puri (4) $4.99 and Chicken 65 $9.99"

# The team's 10 hand-check keywords (fixed top 10), then 10 more Gemini-style ideas
KW = [  # keyword, group, intent, score, why
 ("chicken 65 near me", "dish", "high", 9, "Specific dish search from someone ready to order; Chicken 65 is on the menu at $9.99"),
 ("samosa near UTD", "dish", "high", 9, "Cheap snack search from students; samosas from $2.99"),
 ("chicken tikka Dallas", "dish", "high", 8, "Signature dish in the restaurant's name; big Dallas search"),
 ("seekh kabab North Dallas", "dish", "medium", 7, "Kabab dish + neighborhood; matches the name"),
 ("Indian restaurant near UT Dallas", "cuisine_near_me", "high", 9, "Cuisine + campus landmark; Maps-pack search"),
 ("Pakistani food Richardson", "cuisine_near_me", "high", 8, "Cuisine + neighbor city; few Pakistani competitors"),
 ("Indian food 75252", "cuisine_near_me", "medium", 7, "Zip-code search people type in Maps"),
 ("cheap Indian food near UTD", "occasion_feature", "high", 9, "Budget need; samosas $2.99-$3.99 and Chicken 65 $9.99 fit honestly"),
 ("Indian takeout near me", "occasion_feature", "high", 8, "Takeout need; Order online is on the Google profile"),
 ("best kabab near Richardson", "occasion_feature", "medium", 7, "Comparison search AI assistants answer; 4.2 rating helps"),
 ("onion bhaji near me", "dish", "medium", 6, "Named dish with low competition ($5.99)"),
 ("dal puri dallas", "dish", "medium", 6, "Niche dish many places don't list ($4.99)"),
 ("pakistani restaurant near me", "cuisine_near_me", "high", 8, "Core cuisine + near me"),
 ("indian restaurant north dallas", "cuisine_near_me", "medium", 7, "Cuisine + neighborhood"),
 ("veg samosa near me", "dish", "medium", 6, "Vegetarian variant of the samosa search"),
 ("pakoda near me", "dish", "medium", 5, "Alternate name for onion bhaji"),
 ("indian food open now dallas", "occasion_feature", "medium", 6, "Open-now need; hours 11 AM-9:30 PM daily"),
 ("indian appetizers near me", "dish", "medium", 5, "Matches the snack-heavy menu"),
 ("halal restaurant near utd", "occasion_feature", "medium", 5, "Popular need - ONLY target if halal is confirmed (unknown today)"),
 ("indian dinner richardson", "cuisine_near_me", "low", 4, "Neighbor city search"),
]
TOP = KW[:10]

FOCUS = {
 "chicken 65 near me": ("Chicken 65", "Chicken 65 is a spicy, crispy fried chicken dish from South India, and it is one of the best-value plates on our menu at $9.99."),
 "samosa near UTD": ("Samosas", "We make two kinds of samosa: Chicken Samosa (2 pieces for $2.99) and Veg Samosa (2 pieces for $3.99), a quick, filling snack close to campus."),
 "chicken tikka Dallas": ("Chicken Tikka", "Tikka is in our name. Ask us about today's chicken tikka [owner: confirm chicken tikka item and price before publishing]."),
 "seekh kabab North Dallas": ("Seekh Kabab", "Kababs are in our name. Ask us about seekh kabab [owner: confirm seekh kabab item and price before publishing]."),
 "Indian restaurant near UT Dallas": ("Indian food near UT Dallas", "We are a short drive from the UT Dallas campus, so it is an easy trip for students, staff and visitors."),
 "Pakistani food Richardson": ("Pakistani food near Richardson", "Tikka N Kabab serves Pakistani and Indian favorites in far North Dallas, right next to Richardson."),
 "Indian food 75252": ("Indian food in 75252", "We are a neighborhood Indian and Pakistani restaurant in the 75252 zip code on McCallum Blvd."),
 "cheap Indian food near UTD": ("Affordable Indian food", "You can eat well here without spending much: samosas start at $2.99, Dal Puri is $4.99, Onion Bhaji is $5.99 and Chicken 65 is $9.99."),
 "Indian takeout near me": ("Indian takeout", "Order ahead by phone or with Order online on our Google profile, and pick up hot food on your way home."),
 "best kabab near Richardson": ("Kababs near Richardson", "Google reviewers rate us 4.2 stars. Come try our kababs and decide for yourself [owner: confirm kabab menu items]."),
}

def copy_for(kw, title, lead):
    p = [
        f"Looking for {kw}? {lead}",
        f"{NAME} is at {ADDR}. We are open every day from 11 AM to 9:30 PM, and you can call us at (469) 857-3000 to place an order or ask a question before you come in.",
        f"Our menu includes {MENU}. Every item is cooked to order in our kitchen, so it reaches you hot and crisp. If you are new to this food, start with a plate of samosas and add Chicken 65 if you like heat; if you prefer something milder, Dal Puri and Veg Samosa are good choices.",
        "Many of our guests come from the neighborhoods around McCallum Blvd, Campbell Rd and Coit Rd, from Richardson, and from the UT Dallas campus about two miles away. It is easy to stop by for a snack, pick up food for a group, or sit down for a simple meal with friends or family.",
        f"Google reviewers currently rate {NAME} 4.2 stars across more than 400 reviews. We read every review and use the feedback to keep improving our food and service. If you visit, we would be grateful for an honest review that mentions what you ordered, because it helps other people nearby find dishes they will enjoy.",
        "Before you visit, check our Google Business Profile for photos of the food and the latest posts. Menu prices shown here can change; please call to confirm. Website: [website]. [Owner: add halal status, catering and delivery details here only once confirmed.]",
        f"Come by {NAME} today for {title.lower()} and the rest of our menu. We look forward to cooking for you.",
    ]
    return "\n\n".join(p)

top10 = []
for i, (kw, g, intent, score, why) in enumerate(TOP, 1):
    title, lead = FOCUS[kw]
    tt = f"{title} | {NAME}, North Dallas"
    if len(tt) > 60: tt = f"{title} | {NAME}"[:60]
    kwl = kw.lower()
    top10.append({
        "rank": i, "keyword": kw, "intent_group": g,
        "gbp": {
            "categories": ["Pakistani restaurant", "Indian restaurant", "Kebab shop"],  # today: generic "Restaurant"
            "description_addition": lead,
            "menu_items": ["Chicken 65", "Chicken Samosa (2 pc)", "Veg Samosa (2 pc)", "Onion Bhaji (Pakoda)", "Dal Puri (4)"],
            "photos": [f"Close-up of {title} in natural light", "Storefront and signage on McCallum Blvd", "Menu board with prices", "Counter/dining area (with permission)"],
            "posts": [f"Photo of {title} + 2 lines + 'Call' button", "Weekly post with hours: 11 AM-9:30 PM daily"],
            "review_request": "QR code at the counter and on receipts: 'Enjoyed your food? An honest Google review helps us a lot.' Ask everyone the same way; no discounts or gifts, never ask for a rating or specific words.",
        },
        "website": {"title_tag": tt, "meta_description": f"{title} at {NAME}, 7859 McCallum Blvd, Dallas TX 75252. Open daily 11 AM-9:30 PM. Call (469) 857-3000."[:155],
                    "h1": f"{title} at {NAME}", "page_copy": copy_for(kw, title, lead)},
        "aeo_faqs": [
            {"q": f"Where can I get {re.sub(r"\s+(near .*|dallas|north dallas|richardson|75252)$", "", kw, flags=re.I)} near UT Dallas?", "a": f"{NAME} at 7859 McCallum Blvd Ste 106, Dallas, TX 75252, about 2 miles from UTD. {lead}"},
            {"q": f"What are {NAME}'s hours?", "a": "Open daily 11 AM to 9:30 PM."},
            {"q": f"How do I order from {NAME}?", "a": "Call (469) 857-3000 or visit 7859 McCallum Blvd Ste 106, Dallas, TX 75252."},
        ],
    })

plan = {
 "_note": "OFFLINE fallback plan for Tikka N Kabab, written from facts the team collected on site/Google Maps (name, address, phone, hours, 4.2 rating, 5 menu items + prices). Unknowns are [placeholders]. Ranking data is NOT included: fill data/rankings_manual.csv by hand.",
 "keywords": [{"keyword": k, "intent_group": g, "est_intent": i, "intent_score": s, "why": w} for k, g, i, s, w in KW],
 "top10": top10,
 "gbp_description": (f"{NAME} is a Pakistani and Indian restaurant in far North Dallas on McCallum Blvd, about 2 miles from UT Dallas. "
                     "Known for crispy Chicken 65, chicken and veg samosas, Onion Bhaji (pakoda) and Dal Puri, all made to order at friendly prices "
                     "(samosas from $2.99). Open every day 11 AM to 9:30 PM for dine-in and pickup. Call (469) 857-3000."),
 "faqs": [
  {"q": f"Where is {NAME}?", "a": "7859 McCallum Blvd Ste 106, Dallas, TX 75252, in far North Dallas about 2 miles from UT Dallas."},
  {"q": f"What are {NAME}'s hours?", "a": "Open every day from 11 AM to 9:30 PM."},
  {"q": f"What is {NAME} known for?", "a": "Chicken 65 ($9.99), Chicken Samosa ($2.99 for 2), Veg Samosa ($3.99 for 2), Onion Bhaji ($5.99) and Dal Puri ($4.99 for 4)."},
  {"q": f"Is {NAME} affordable?", "a": "Yes. Samosas start at $2.99 and most snacks are under $6; Chicken 65 is $9.99."},
  {"q": f"What is {NAME}'s phone number?", "a": "(469) 857-3000."},
 ],
}
out = ROOT / "sample_output" / "tikka_n_kabab.plan.json"
out.write_text(json.dumps(plan, indent=2))
print("wrote", out)
