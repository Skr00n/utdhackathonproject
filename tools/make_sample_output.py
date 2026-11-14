import json
N="Sample Chettinad Kitchen"
kws=[
("chicken biryani near me","dish","high",10,"Top dish search; people ready to order now"),
("chettinad chicken richardson","dish","high",9,"Signature dish + city = strong local intent"),
("dosa near me","dish","high",9,"High-volume South Indian dish search"),
("best biryani in richardson tx","dish","high",9,"'Best' + dish + city is a classic Maps query"),
("masala dosa richardson","dish","medium",7,"Specific dosa variant searchers"),
("spicy south indian chicken curry","dish","medium",6,"Describes Chettinad food without knowing the name"),
("goat biryani dallas","dish","medium",6,"Broader metro dish search"),
("south indian restaurant near me","cuisine_near_me","high",10,"Core cuisine + near me"),
("chettinad restaurant near me","cuisine_near_me","high",8,"Exact niche match, low competition"),
("indian restaurant richardson tx","cuisine_near_me","high",9,"Broad cuisine + city"),
("tamil food near me","cuisine_near_me","medium",7,"Chettinad is Tamil cuisine; diaspora search"),
("indian food open now","cuisine_near_me","high",8,"Time-sensitive intent"),
("halal indian restaurant richardson","occasion_feature","high",9,"Halal is a must-have filter for many diners"),
("indian lunch buffet near me","occasion_feature","high",9,"Lunch buffet is a strong weekday driver"),
("late night food near ut dallas","occasion_feature","high",8,"Open till 11 PM + student audience"),
("cheap eats near ut dallas","occasion_feature","medium",7,"Students on a budget"),
("indian food open late richardson","occasion_feature","high",8,"Late-hours feature + city"),
("halal biryani near me","occasion_feature","high",9,"Combines feature + top dish"),
("group dinner indian restaurant richardson","occasion_feature","medium",6,"Groups / student orgs"),
("vegetarian south indian food richardson","occasion_feature","medium",6,"Dosa makes it veg-friendly"),
]
keywords=[dict(keyword=k,intent_group=g,est_intent=e,intent_score=s,why=w) for k,g,e,s,w in kws]
top_names=["chicken biryani near me","south indian restaurant near me","halal indian restaurant richardson","indian lunch buffet near me","chettinad chicken richardson","dosa near me","late night food near ut dallas","indian restaurant richardson tx","halal biryani near me","chettinad restaurant near me"]
g={k:gg for k,gg,*_ in kws}
COMMON=("Our kitchen follows the cooking of the Chettinad region of Tamil Nadu, known for freshly roasted and ground spices: black pepper, fennel, star anise, dried red chilies, kalpasi (stone flower) and curry leaves. We roast our masalas in small batches every morning, so the flavor is deep and aromatic rather than just hot. If you prefer milder food, tell your server and the kitchen will adjust the spice level for you.\n\n"
"The menu centers on three dishes our regulars come back for. Chicken biryani [price] is layered with seeded basmati rice, slow-cooked chicken, mint and fried onions, and it comes with raita and salna. Chettinad chicken [price] is a dry-roasted pepper curry that pairs well with parotta or steamed rice. Dosa [price] is a thin, crisp rice-and-lentil crepe served with sambar and fresh chutneys, with masala, ghee roast and onion versions available.\n\n"
"All of our meat is halal. On weekdays we run a lunch buffet with rotating curries, biryani, dosa made to order and dessert, a quick option if you are coming from class or the office. We stay open until 11 PM, so dinner after a late lab or a game is easy.\n\n"
"You will find us in Richardson, TX 75080, a short drive from the UT Dallas campus. Dine in, pick up, or call ahead for large group orders. Hours: open daily from 11 AM to 11 PM. See the full menu with current prices on our menu page, and check our Google Business Profile for photos and today's specials.\n\n")
INTRO={
"chicken biryani near me":("Chicken Biryani in Richardson, Made the Chettinad Way","Looking for chicken biryani near you in Richardson? Our biryani is cooked in the Chettinad style, with whole spices roasted in-house and seeraga samba or basmati rice layered over tender halal chicken. It is the dish most guests order on their first visit."),
"south indian restaurant near me":("South Indian Food in Richardson, TX","If you are searching for a South Indian restaurant close to Richardson or UT Dallas, we cook the food of Tamil Nadu's Chettinad region: peppery curries, biryani, dosa and idli, made fresh every day."),
"halal indian restaurant richardson":("Halal Indian Restaurant in Richardson","Every meat dish on our menu is made with halal chicken and goat, so you can order the full menu with confidence. We are a family-style South Indian restaurant in Richardson serving Chettinad cooking."),
"indian lunch buffet near me":("Weekday South Indian Lunch Buffet in Richardson","Our weekday lunch buffet is built for people with an hour to eat: biryani, two or three Chettinad curries, a vegetarian dish, dosa made to order at the counter, and dessert, at one set price [price]."),
"chettinad chicken richardson":("Chettinad Chicken in Richardson, TX","Chettinad chicken is the signature dish of our kitchen and the reason we opened in Richardson. It is a dark, pepper-forward curry made with a masala of more than ten spices that we roast and grind ourselves."),
"dosa near me":("Crispy Dosa in Richardson, Near UT Dallas","Craving a hot, crispy dosa nearby? We make every dosa to order on a cast-iron tawa from batter fermented overnight, and serve it with sambar and coconut, tomato and mint chutneys."),
"late night food near ut dallas":("Late-Night South Indian Food Near UT Dallas","Studying late or just finished practice? We are open until 11 PM every day, a few minutes from UT Dallas, with hot biryani, dosa and Chettinad curries for dine-in or pickup."),
"indian restaurant richardson tx":("Indian Restaurant in Richardson, TX: Chettinad Cuisine","Among Indian restaurants in Richardson, TX, we focus on one region's cooking, Chettinad from South India, instead of a generic menu. That focus shows up in the spice blends, the biryani and the dosa."),
"halal biryani near me":("Halal Biryani in Richardson","Our biryani is made only with halal chicken and goat, cooked dum-style so the rice absorbs the masala. Guests who want halal biryani nearby in Richardson and around UT Dallas order it for dine-in, pickup and parties."),
"chettinad restaurant near me":("A Chettinad Restaurant in Richardson","Chettinad restaurants are rare in North Texas. We bring the cooking of Karaikudi and the Chettinad region to Richardson: roasted spice masalas, pepper chicken, kuzhambu, biryani and dosa."),
}
def faqs_for(k):
    base={
"chicken biryani near me":[("Does Sample Chettinad Kitchen serve chicken biryani?","Yes. Chicken biryani is a signature dish, made Chettinad-style with halal chicken and served with raita and salna."),("Is the chicken biryani halal?","Yes, all meat at Sample Chettinad Kitchen is halal."),("Can I order biryani for pickup in Richardson?","Yes. Call ahead or order at the counter for pickup in Richardson, TX 75080.")],
"south indian restaurant near me":[("What kind of food does Sample Chettinad Kitchen serve?","South Indian food from the Chettinad region of Tamil Nadu: biryani, Chettinad chicken, dosa and more."),("Where is Sample Chettinad Kitchen?","Richardson, TX 75080, a short drive from UT Dallas."),("Does it have vegetarian options?","Yes. Dosa and several curries are vegetarian.")],
"halal indian restaurant richardson":[("Is Sample Chettinad Kitchen halal?","Yes, all chicken and goat served are halal."),("Is the lunch buffet halal?","Yes, every meat dish on the buffet is halal."),("What halal dishes are popular?","Chicken biryani and Chettinad chicken are the most ordered halal dishes.")],
"indian lunch buffet near me":[("Does Sample Chettinad Kitchen have a lunch buffet?","Yes, a South Indian lunch buffet runs on weekdays."),("What is on the lunch buffet?","Biryani, rotating Chettinad curries, a vegetarian dish, made-to-order dosa and dessert."),("Is the buffet good for a quick lunch near UT Dallas?","Yes. It is a few minutes from campus and designed for a one-hour lunch.")],
"chettinad chicken richardson":[("What is Chettinad chicken?","A pepper-forward South Indian chicken curry made with freshly roasted Chettinad spices."),("Where can I get Chettinad chicken in Richardson?","Sample Chettinad Kitchen in Richardson, TX 75080 serves it daily."),("Is Chettinad chicken very spicy?","It is peppery; the kitchen can make it milder on request.")],
"dosa near me":[("Does Sample Chettinad Kitchen make dosa?","Yes, dosa is made to order and served with sambar and chutneys."),("What dosa types are available?","Plain, masala, onion and ghee roast dosa."),("Is dosa vegetarian?","Yes, dosa is vegetarian and made from fermented rice and lentil batter.")],
"late night food near ut dallas":[("How late is Sample Chettinad Kitchen open?","Open until 11 PM daily."),("Is it close to UT Dallas?","Yes, it is in Richardson, a short drive from campus."),("Can I get takeout late at night?","Yes, pickup is available until closing.")],
"indian restaurant richardson tx":[("What Indian cuisine does Sample Chettinad Kitchen specialize in?","Chettinad cuisine from South India."),("What are the most popular dishes?","Chicken biryani, Chettinad chicken and dosa."),("Does it take reservations?","Yes, reservations are accepted, including for groups.")],
"halal biryani near me":[("Is the biryani at Sample Chettinad Kitchen halal?","Yes, chicken and goat biryani are made with halal meat."),("Can I order biryani for a party?","Yes, call ahead for large or party orders."),("What comes with the biryani?","Raita and salna.")],
"chettinad restaurant near me":[("Is there a Chettinad restaurant in Richardson?","Yes, Sample Chettinad Kitchen in Richardson, TX 75080."),("What makes Chettinad food different?","Freshly roasted and ground spices like black pepper, fennel and kalpasi."),("What should I order first?","Chettinad chicken with parotta, or the chicken biryani.")],
    }[k]
    return [dict(q=q,a=a) for q,a in base]
GBPCAT={"dish":["South Indian restaurant","Indian restaurant","Halal restaurant"],"cuisine_near_me":["South Indian restaurant","Indian restaurant","Tamil restaurant"],"occasion_feature":["South Indian restaurant","Halal restaurant","Buffet restaurant"]}
top=[]
for i,k in enumerate(top_names,1):
    h1,intro=INTRO[k]
    copy=intro+"\n\n"+COMMON+"Questions before you visit? Read the FAQ below or call us. We would love to cook for you."
    short=h1.split(":")[0]
    title=(short+" | "+N)
    if len(title)>60: title=short[:60]
    top.append(dict(rank=i,keyword=k,intent_group=g[k],
      gbp=dict(categories=GBPCAT[g[k]],
        description_addition={"dish":"Signature dish highlighted in the description in plain language, e.g. 'Known for Chettinad-style chicken biryani and pepper chicken.'","cuisine_near_me":"State the cuisine and location clearly: 'Chettinad (South Indian) restaurant in Richardson, near UT Dallas.'","occasion_feature":"Mention the real feature once: halal meat, weekday lunch buffet, open until 11 PM."}[g[k]],
        menu_items={"dish":["Chicken Biryani","Chettinad Chicken","Masala Dosa","Goat Biryani"],"cuisine_near_me":["Chettinad Chicken","Chicken Biryani","Dosa","Idli"],"occasion_feature":["Lunch Buffet (weekdays)","Halal Chicken Biryani","Late-night Dosa"]}[g[k]],
        photos=[f"Close-up of the dish/experience for '{k}' in natural light","Interior with guests (with permission)","Exterior + signage so people recognize the storefront","Menu board showing prices"],
        posts=[f"Google Post: photo + 2 lines about {k.split(' near')[0]} with a 'Call' button",f"Weekly 'today's special' post mentioning hours (open till 11 PM)"],
        review_request="Add a QR code on receipts/tables: 'Enjoyed your meal? An honest Google review helps us a lot.' Ask every customer the same way; no discounts or gifts for reviews, and never ask for a specific rating or wording."),
      website=dict(title_tag=title,meta_description=intro[:150].rsplit(" ",1)[0]+"...",h1=h1,page_copy=copy),
      aeo_faqs=faqs_for(k)))
plan=dict(_note="Hand-written sample output for demo/offline mode (no Gemini call). Prices shown as [price] placeholders; phone and street address must be filled from restaurants.csv before publishing.",
  keywords=keywords,top10=top,
  gbp_description="Sample Chettinad Kitchen is a South Indian restaurant in Richardson, TX, serving the cooking of Tamil Nadu's Chettinad region. Known for chicken biryani, Chettinad pepper chicken and crispy dosa made to order. All meat is halal. Weekday lunch buffet, and we're open daily until 11 PM, a short drive from UT Dallas. Dine in, pickup, and group orders welcome.",
  faqs=[dict(q="Is Sample Chettinad Kitchen halal?",a="Yes. All chicken and goat served at Sample Chettinad Kitchen are halal."),
        dict(q="What are the hours of Sample Chettinad Kitchen?",a="Open daily from 11 AM to 11 PM."),
        dict(q="Does Sample Chettinad Kitchen have a lunch buffet?",a="Yes, a South Indian lunch buffet is served on weekdays."),
        dict(q="Where is Sample Chettinad Kitchen located?",a="Richardson, TX 75080, a short drive from UT Dallas."),
        dict(q="What dishes is Sample Chettinad Kitchen known for?",a="Chicken biryani, Chettinad chicken and dosa.")])
open("sample_output/sample_chettinad_kitchen.plan.json","w").write(json.dumps(plan,indent=2))
