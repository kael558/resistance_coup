from src.utils.api_interface import client

def generate_personality(name: str, gender: str):
    system_msg = f"""Generate a personality for a {gender} named {name}. 
They are playing the board game Coup, so you can include elements that will make them interesting players. 

You can be creative with personalities, ranging from a calm, strategic to a loud, aggressive player.

You may even include various emotional tendencies...

Just generate the personality. Don't say anything else like 'Sure, here is a personality'."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
        ],
        temperature=1.0
    )

    return response.choices[0].message.content