import json
import os

import boto3
from dotenv import load_dotenv

load_dotenv()

if not os.getenv('AWS_ACCESS_KEY_ID') or not os.getenv('AWS_SECRET_ACCESS_KEY'):
    raise RuntimeError('AWS credentials are not set. Add them to your .env file.')

# boto3 reads the key, secret and region from the environment.
client = boto3.client('comprehendmedical')


result = client.detect_entities_v2(
    Text= """
    
**Outpatient Clinic – Doctor-Patient Conversation**

**Doctor:** Good morning. Please come in and have a seat. What is your name?
**Patient:** Good morning, Doctor. My name is Gaia.
**Doctor:** Nice to meet you, Gaia. How old are you?
**Patient:** I’m 29 years old.
**Doctor:** Thank you. What brings you here today?
**Patient:** I’ve been feeling really unwell for the past four days. I have a high fever that keeps coming and going, and my body aches a lot—especially my joints and muscles. It feels like someone is crushing my bones.
**Doctor:** I see. How high has the fever been?
**Patient:** Around 102–103°F. I’ve been taking paracetamol, but it only brings it down for a few hours, then it shoots up again. I also have a severe headache, and there’s this constant pain behind my eyes. It hurts when I look around or move my eyes.
**Doctor:** Any other symptoms? Nausea, vomiting, loss of appetite, or rash?
**Patient:** Yes. I’ve felt nauseous, and I vomited twice yesterday. I don’t feel like eating anything. No rash that I’ve noticed so far. I’ve also felt very tired and weak. Sometimes I get chills.
**Doctor:** Have you noticed any bleeding—from gums, nose, or under the skin? Any black stools or unusual bruising?
**Patient:** No, nothing like that. Just the fever, body pain, headache, and feeling drained.
**Doctor:** Any recent travel, mosquito bites, or anyone at home with similar symptoms?
**Patient:** We live in an area with a lot of mosquitoes. I do get bitten quite often. No one else at home is sick right now.
**Doctor:** All right. Let me examine you.  
*(Checks temperature, pulse, blood pressure, looks for rash, checks for tenderness, and assesses hydration.)*  
Your temperature is still elevated, pulse is a bit rapid, and you look dehydrated. There’s some mild tenderness around the muscles. I’m going to order some blood tests and give you supportive medicines.

The symptoms you’re describing—high fever, severe body and joint pain, headache with pain behind the eyes, nausea, and fatigue—are classic for dengue fever, especially with the ongoing monsoon and mosquito exposure. We need the blood reports to confirm, but clinically it looks very suggestive. Dengue can sometimes lower platelet counts, so we have to monitor that closely.

**Patient:** Dengue? I didn’t think of that. I thought it was just a viral fever or maybe malaria.

**Doctor:** That’s understandable. Many people present like this. The good news is that most cases of dengue are manageable with proper rest, hydration, and monitoring. Avoid aspirin or ibuprofen—they can increase bleeding risk. Stick only to the medicines I’m prescribing.


---

**Investigations Advised:**

1. Complete Blood Count (CBC) with Platelet Count & Hematocrit  
2. Dengue NS1 Antigen  
3. Dengue IgM & IgG Antibodies  
4. Liver Function Tests (LFT)  
5. Random Blood Sugar  

*(Please get these done today and share the reports as soon as they are ready.)*

---

**Prescription (Supportive Treatment):**

**Patient Name:** Gaia  
**Age/Sex:** 29 years / Female  
**Date:** ________________

1. **Tab. Paracetamol 650 mg**  
   – 1 tablet every 6 hours if fever or body pain is present  
   – Maximum 4 tablets in 24 hours  

2. **ORS (Oral Rehydration Solution)**  
   – 1 sachet in 1 litre of clean water  
   – Drink frequently throughout the day (aim for 3–4 litres of fluids daily)

3. **Syp. Ondansetron 4 mg / 5 ml** (or Tab. Ondansetron 4 mg)  
   – 5 ml (or 1 tablet) twice a day if nausea/vomiting is present  

4. **Tab. Pantoprazole 40 mg**  
   – 1 tablet once daily before breakfast (for 5 days)  

**Advice:**
- Complete bed rest  
- Plenty of oral fluids (ORS, coconut water, lemon water, soups)  
- Soft, light diet as tolerated  
- Do **not** take Aspirin, Ibuprofen, Diclofenac or any other painkiller  
- Monitor temperature and urine output  
- Report immediately if: bleeding from any site, severe abdominal pain, persistent vomiting, extreme weakness, or reduced urine output
---

**Doctor:** Start these medicines and fluids right away. Get the blood tests done today. I’ll call you once the reports come. Any questions?

**Patient:** No, Doctor. Thank you so much. I’ll follow everything carefully.

**Doctor:** Take care, Gaia. Rest well and stay hydrated."""
    )

entities = result['Entities']

with open('entities.json', 'w', encoding='utf-8') as f:
    json.dump(entities, f, indent=2, ensure_ascii=False)

print(f'Wrote {len(entities)} entities to entities.json')
