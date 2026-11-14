"""Writes sample_output/tikka_n_kabab.plan.json: the OFFLINE fallback plan for Tikka N Kabab,
written only from the real facts the team collected (name, address, phone, hours, 4.2 rating,
5 menu items with prices). Unknowns stay as [placeholders]. Run: python tools/make_tikka_plan.py"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Tikka N Kabab"
ADDR = "7859 McCallum Blvd Ste 106, Dallas, TX 75252"
MENU = ("appetizers like Chicken Samosa and Beef Samosa ($3.99 for 2), Veg Samosa, Onion Bhajji (Pakoda), Dal Puri and Chicken 65 ($9.99); "
        "curries like Butter Chicken, Chicken Tikka Masala, Chicken Kadahi and Chicken Keema ($12.99 each), Beef Nihari and Shrimp Masala ($14.99); "
        "plus Lahori Fish, Gobhi Manchurian, biryani, BBQ/grill, wraps, chaat, naan and paratha, dessert and drinks")
SITE = "https://www.tikkankababtx.com"

# The team's 10 hand-check keywords (fixed top 10), then 10 more Gemini-style ideas
KW = [  # team's final 10 (fixed top 10), then 10 more ideas
 ("chicken 65 near me", "dish", "high", 9, "Dish search from someone ready to order; Chicken 65 is $9.99"),
 ("butter chicken near UTD", "dish", "high", 9, "Most-searched curry + campus; Butter Chicken $12.99"),
 ("beef nihari Dallas", "dish", "high", 8, "Pakistani signature dish few places serve; on the menu"),
 ("chicken tikka masala Richardson", "dish", "high", 8, "Classic curry + neighbor city; $12.99"),
 ("Pakistani restaurant North Dallas", "cuisine_near_me", "high", 9, "Core cuisine + neighborhood; Maps-pack search"),
 ("Indian restaurant near UT Dallas", "cuisine_near_me", "high", 9, "Cuisine + campus landmark"),
 ("Indian BBQ kabab 75252", "cuisine_near_me", "medium", 7, "BBQ/grill menu + zip code; matches the name"),
 ("cheap Indian food near UTD", "occasion_feature", "high", 9, "Budget need; samosas $3.99, Chicken 65 $9.99"),
 ("Indian takeout near me", "occasion_feature", "high", 8, "Takeout need; Order online on Google + website"),
 ("samosa near me", "occasion_feature", "high", 8, "Snack need; chicken, beef and veg samosas"),
 ("chicken kadahi near me", "dish", "medium", 7, "Pakistani curry search; $12.99"),
 ("shrimp masala dallas", "dish", "medium", 6, "Seafood curry; $14.99"),
 ("lahori fish near me", "dish", "medium", 6, "Lahore-style fried fish; niche, easy to win"),
 ("chicken biryani north dallas", "dish", "high", 8, "Biryani is a top Indian/Pakistani search; Biryani/Rice on menu"),
 ("halal restaurant near utd", "occasion_feature", "medium", 5, "Popular need - ONLY target if halal is confirmed (unknown today)"),
 ("gobhi manchurian near me", "dish", "medium", 5, "Indo-Chinese veg favorite"),
 ("chicken keema dallas", "dish", "medium", 5, "Minced chicken curry; $12.99"),
 ("indian food open now dallas", "occasion_feature", "medium", 6, "Open-now need; 11 AM-9:30 PM daily"),
 ("chaat near me", "dish", "medium", 5, "Chaat category on the menu"),
 ("indian dinner richardson", "cuisine_near_me", "low", 4, "Neighbor city search"),
]
TOP = KW[:10]

FOCUS = {
 "chicken 65 near me": ("Chicken 65", "Chicken 65 is a spicy, crispy fried chicken appetizer, and one of the best-value plates on our menu at $9.99."),
 "butter chicken near UTD": ("Butter Chicken", "Our Butter Chicken is tender chicken in a creamy tomato sauce, $12.99, a short drive from UT Dallas."),
 "beef nihari Dallas": ("Beef Nihari", "Beef Nihari is a slow-cooked Pakistani stew that many Dallas restaurants don't serve. Find it in our Meat Curries."),
 "chicken tikka masala Richardson": ("Chicken Tikka Masala", "Chicken Tikka Masala, $12.99, is a classic curry on our menu, just across the line from Richardson."),
 "Pakistani restaurant North Dallas": ("Pakistani food in North Dallas", "Tikka N Kabab serves Pakistani and Indian food in far North Dallas: curries, biryani, BBQ/grill, wraps and chaat."),
 "Indian restaurant near UT Dallas": ("Indian food near UT Dallas", "We are a short drive from the UT Dallas campus, an easy trip for students, staff and visitors."),
 "Indian BBQ kabab 75252": ("BBQ and kababs in 75252", "Our Bar B Que/Grill and BBQ Wraps/Rolls menus bring kabab-house cooking to the 75252 zip code on McCallum Blvd."),
 "cheap Indian food near UTD": ("Affordable Indian food", "You can eat well here without spending much: samosas are $3.99 for two and Chicken 65 is $9.99."),
 "Indian takeout near me": ("Indian takeout", "Order ahead online at tikkankababtx.com or with Order online on our Google profile, or call (469) 857-3000."),
 "samosa near me": ("Samosas", "We make Chicken Samosa and Beef Samosa ($3.99 for 2) and Veg Samosa, golden and crisp."),
}

def copy_for(kw, title, lead):
    p = [
        f"Looking for {kw}? {lead}",
        f"{NAME} is at {ADDR}. We are open every day from 11 AM to 9:30 PM, and you can call us at (469) 857-3000 to place an order or ask a question before you come in.",
        f"Our menu includes {MENU}. Every item is cooked to order in our kitchen, so it reaches you hot and crisp. If you are new to this food, start with a plate of samosas and add Chicken 65 if you like heat; if you prefer something milder, Dal Puri and Veg Samosa are good choices.",
        "Many of our guests come from the neighborhoods around McCallum Blvd, Campbell Rd and Coit Rd, from Richardson, and from the UT Dallas campus about two miles away. It is easy to stop by for a snack, pick up food for a group, or sit down for a simple meal with friends or family.",
        f"Google reviewers currently rate {NAME} 4.2 stars across more than 400 reviews. We read every review and use the feedback to keep improving our food and service. If you visit, we would be grateful for an honest review that mentions what you ordered, because it helps other people nearby find dishes they will enjoy.",
        "Before you visit, check our Google Business Profile for photos of the food and the latest posts. Menu prices shown here can change; please call to confirm. Full menu and online ordering: https://www.tikkankababtx.com. [Owner: add halal status and catering details here only once confirmed.]",
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
            "menu_items": ["Chicken 65 $9.99", "Butter Chicken $12.99", "Chicken Tikka Masala $12.99", "Beef Nihari", "Chicken Samosa (2) $3.99"],
            "photos": [f"Close-up of {title} in natural light", "Storefront and signage on McCallum Blvd", "Menu board with prices", "Counter/dining area (with permission)"],
            "posts": [f"Photo of {title} + 2 lines + 'Call' button", "Weekly post with hours: 11 AM-9:30 PM daily"],
            "review_request": "QR code at the counter and on receipts: 'Enjoyed your food? An honest Google review helps us a lot.' Ask everyone the same way; no discounts or gifts, never ask for a rating or specific words.",
        },
        "website": {"title_tag": tt, "meta_description": f"{title} at {NAME}, 7859 McCallum Blvd, Dallas TX 75252 near UTD. Open daily 11 AM-9:30 PM. Order online or call (469) 857-3000."[:155],
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
                     "Known for Chicken 65, Butter Chicken, Chicken Tikka Masala, Beef Nihari, BBQ/grill and kababs, biryani and samosas, at friendly prices "
                     "(samosas $3.99, curries $12.99). Open every day 11 AM to 9:30 PM. Order online at tikkankababtx.com or call (469) 857-3000."),
 "faqs": [
  {"q": f"Where is {NAME}?", "a": "7859 McCallum Blvd Ste 106, Dallas, TX 75252, in far North Dallas about 2 miles from UT Dallas."},
  {"q": f"What are {NAME}'s hours?", "a": "Open every day from 11 AM to 9:30 PM."},
  {"q": f"What is {NAME} known for?", "a": "Pakistani and Indian food: Chicken 65 ($9.99), Butter Chicken and Chicken Tikka Masala ($12.99), Beef Nihari, BBQ/grill kababs, biryani and samosas ($3.99 for 2)."},
  {"q": f"Is {NAME} affordable?", "a": "Yes. Samosas are $3.99 for two, Chicken 65 is $9.99 and most curries are $12.99."},
  {"q": f"Can I order {NAME} online?", "a": "Yes, at https://www.tikkankababtx.com or with Order online on Google. Phone: (469) 857-3000."},
 ],
}
out = ROOT / "sample_output" / "tikka_n_kabab.plan.json"
out.write_text(json.dumps(plan, indent=2))
print("wrote", out)
