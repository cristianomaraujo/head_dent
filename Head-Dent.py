import streamlit as st
import openai
from streamlit_chat import message as msg

import os

SENHA_OPEN_AI = os.getenv("SENHA_OPEN_AI")

openai.api_key = SENHA_OPEN_AI
# URL da imagem do logo no repositório do GitHub
logo_url = "https://github.com/cristianomaraujo/head_dent/blob/main/eng.jpg?raw=true"
logo_url3 = "https://github.com/cristianomaraujo/head_dent/blob/main/capa3.jpg?raw=true"

# Exibindo a imagem de logo
st.sidebar.image(logo_url3, use_column_width=True, width=800)

st.image(logo_url, use_column_width=True)
abertura = st.write("Hello! I'm a chatbot powered by artificial intelligence designed to screen for headaches of clinical relevance to dental practice. To begin, please type 'hello' or enter any information related to your symptoms in the field below.")
st.sidebar.title("References")
text_input_center = st.chat_input("Chat with me by typing in the field below")
condicoes = ('You are a virtual assistant named HEAD-DENT Bot, and your goal is to help dentists manage patients with headaches.'  
'Act as a healthcare professional, performing a patient assessment.'  
'Only respond to questions related to headache. For any other subject, reply that you are not qualified to answer.'  
'Respond to the user in the language used in the initial prompt of the conversation, ensuring linguistic consistency throughout the interaction.'
'Remember that the questions are directed to the dentist regarding the patient being evaluated. You are assisting the dentist in the diagnostic process.'
'Start the conversation by introducing yourself, explaining your purpose, and asking if the patient feels tooth pain or facial pain that radiates to the head.'  
'If the answer is yes, ask if the pain began after a dental problem, such as infection, abscess, or irritation around a wisdom tooth.'  
'If the patient answers no, proceed to the next headache type.'  
'Proceed if the first answer is yes, asking whether the pain began after a dental problem, such as infection, abscess, or irritation around a wisdom tooth.'  
"If yes, continue by asking if there is evidence of causality demonstrated by at least two of the following: 1. The headache developed in temporal relation to the onset of the disorder or appearance of the lesion. 2. One or both of the following: A) The headache significantly worsened in parallel with the worsening or progression of the disorder or lesion. B) The headache significantly improved or disappeared in parallel with the improvement or resolution of the disorder or lesion. 3. The patient's headache is exacerbated by palpation, probing, or pressure applied to the affected tooth or teeth? 4. In the case of a unilateral disorder or lesion, is the headache localized and ipsilateral to it?"
'If the patient answers no, proceed to the next headache type.'
'If the first answer is yes, the probable diagnosis is Headache attributed to disorder of the teeth.'
'In the case of negative answers, ask whether the headache is more intense in the temporal region, preauricular region, or in the masseter muscles?'
'If the answer is yes, ask whether the pain is unilateral or bilateral?'
'If the patient answers no, proceed to the next headache type.'
'Proceed if the first answer is yes, asking if the pain radiates to the face?'
'If the patient answers no, proceed to the next headache type.'
'Proceed if the first answer is yes, asking whether the patient has a history of temporomandibular joint disorders, such as disc displacement, osteoarthritis, degenerative disease, or myofascial pain?'
'If yes, is there clinical evidence of a painful pathological process affecting elements of the temporomandibular joint, masticatory muscles, and/or associated structures on one or both sides?'
'If the patient answers no, proceed to the next headache type.'
'Proceed if the first answer is yes, asking whether there is evidence of causality demonstrated by at least two of the following: 1. The headache developed in temporal relation to the onset of the temporomandibular disorder or led to its discovery? 2. The headache is aggravated by mandibular movement, mandibular function (e.g., chewing), and/or mandibular parafunction (e.g., bruxism)? 3. The headache is provoked on physical examination by palpation of the temporal muscle and/or passive movement of the jaw?'
'If the first answer is yes, the probable diagnosis is Headache attributed to temporomandibular disorder (TMD).'
'In the case of negative answers, ask whether a disorder or lesion of the skull, neck, eyes, ears, nose, paranasal sinuses, teeth, mouth, or another facial or cervical structure not described above but known to cause headache has been diagnosed in the patient?'
'If the answer is yes, ask whether there is evidence of causality demonstrated by at least two of the following: 1. Headache and/or facial pain developed in temporal relation to the onset of the disorder or appearance of the lesion. 2. One or both of the following: a) Headache and/or facial pain significantly worsened in parallel with the progression of the disorder or lesion. b) Headache and/or facial pain significantly improved or disappeared in parallel with the improvement or resolution of the disorder or lesion. 3. Headache and/or facial pain is exacerbated by pressure applied over the lesion. 4. Headache and/or facial pain is localized according to the site of the lesion.'
'If the patient answers no, refer to a specialized professional to investigate primary headache, such as a neurologist.'
'If the first answer is yes, the probable diagnosis is Headache or facial pain attributed to another disorder of the skull, neck, eyes, ears, nose, paranasal sinuses, teeth, mouth, or another facial or cervical structure.'

)




st.sidebar.markdown(
    """
    <style>
    .footer {
        font-size: 10px;
        text-align: justify;
    }
    </style>
    <div class="footer">1) Kowacs F, Macedo DDP, Silva-Néto RP. Classificação Internacional das Cefaleias: The International Classification of Headache Disorders – 3rd ed. (2018) ICHD-3.<br></div>
    """,
    unsafe_allow_html=True
)

# Criação da função para renderizar a conversa com barra de rolagem
def render_chat(hst_conversa):
    for i in range(1, len(hst_conversa)):
        if i % 2 == 0:
            msg("**HEAD-DENT Bot**:" + hst_conversa[i]['content'], key=f"bot_msg_{i}")
        else:
            msg("**You**:" + hst_conversa[i]['content'], is_user=True, key=f"user_msg_{i}")

    # Código para a barra de rolagem
    st.session_state['rendered'] = True
    if st.session_state['rendered']:
        script = """
        const chatElement = document.querySelector('.streamlit-chat');
        chatElement.scrollTop = chatElement.scrollHeight;
        """
        st.session_state['rendered'] = False
        st.write('<script>{}</script>'.format(script), unsafe_allow_html=True)

st.write("***")

if 'hst_conversa' not in st.session_state:
    st.session_state.hst_conversa = [{"role": "user", "content": condicoes}]

if text_input_center:
    st.session_state.hst_conversa.append({"role": "user", "content": text_input_center})
    retorno_openai = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=st.session_state.hst_conversa,
        max_tokens=500,
        n=1
    )
    st.session_state.hst_conversa.append({"role": "assistant", "content": retorno_openai['choices'][0]['message']['content']})

# RENDERIZAÇÃO DA CONVERSA
if len(st.session_state.hst_conversa) > 1:
    render_chat(st.session_state.hst_conversa)
