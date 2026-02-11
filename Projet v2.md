# 4. Projet Master 2 IA : Simulateur d'Arnaque Dynamique & Interactif

## 4.0 Consignes Administratives et de Rendu (CRITIQUE)

Avant de parler technique, voici les règles **éliminatoires** pour le rendu :

1. **Dépôt GitHub Public :** Le code doit être hébergé sur un repository GitHub public.
    
2. **Sécurité des Clés (Zéro Tolérance) :**
    
    - **AUCUNE clé d'API (OpenAI, HuggingFace, etc.) ne doit être commitée.**
        
    - Utilisez un fichier `.env` ajouté au `.gitignore`.
        
    - _Pénalité :_ Si une clé est trouvée dans l'historique des commits, le projet sera pénalisé.
        
3. **Identification :** Le fichier `README.md` doit impérativement contenir les **Noms et Prénoms** de tous les membres du groupe. Sans cela, pas de notation.
4. Le `README.md` est votre rapport, c'est ce que je note
    

---

## 4.1 Architecture du Système : "Le Théâtre de l'Arnaque"

Le système n'est plus un simple chatbot, c'est une simulation orchestrée par plusieurs agents.

### 4.1.1 Les Acteurs (Agents LLM)

1. **L'Agent "Victime" (Mr Jean Dubois) :**
    
    - **Rôle :** Exécute le Persona (vieux monsieur, 78 ans, aigri, tendance à s'enerver).
        
    - **Spécificité :** Il a accès à des **Outils (Tools)** pour générer des bruitages (toux, chien, sonnette).
        
    - **Entrée :** Le texte de l'arnaqueur + L'objectif courant + Contexte audience.
        
2. **L'Agent "Directeur de Scénario" (Superviseur) :**
    
    - **Rôle :** Il ne parle pas. Il analyse la conversation en arrière-plan.
        
    - **Tâche :** Il compare l'état de la discussion avec un "Script d'Arnaque Type" (ex: Support Technique Microsoft).
        
    - **Sortie :** Il met à jour l'**Objectif Courant** de Mr Dubois (ex: "Il demande l'accès au PC -> Feindre de ne pas trouver le bouton 'Démarrer'").
        
3. **L'Agent "Modérateur Audience" :**
    
    - **Rôle :** Filtre et sélectionne les propositions de l'audience.
        

---

## 4.2 Fonctionnalités Clés et Workflow

### 4.2.1 Le Scénario Dynamique (Scripted Flow)

L'interaction suit un script classique (ex: Arnaque au Compte Bancaire ou Tech Support).

- **Boucle de contrôle :** À chaque échange, le _Directeur_ évalue si l'étape du script est franchie. Si oui, il pousse un nouveau contexte dans le _System Prompt_ de la Victime.
    

### 4.2.2 L'Interaction Audience (Bifurcation)

Pour rendre la démo vivante, l'audience peut influencer le destin de l'arnaqueur.

1. **Input :** Les spectateurs proposent des événements via une interface (console ou simple input texte).
    
2. **Sélection (LLM) :** L'Agent _Modérateur_ reçoit toutes les idées, en élimine les inappropriées et en sélectionne **3 cohérentes** avec la situation.
    
3. **Vote :** Un vote (simulé ou réel) détermine l'événement gagnant.
    
4. **Conséquence :** L'objectif de la Victime change temporairement (ex: "Quelqu'un sonne à la porte, va ouvrir et laisse l'arnaqueur attendre 2 minutes").
    

### 4.2.3 Audio et MCP (Model Context Protocol)

La victime doit être "entendue" dans son environnement.

- **MCP Server / Tools :** Implémentez une liste d'outils que le LLM peut appeler **au lieu de répondre par du texte seul**.
    
- **Liste de Bruits (Soundboard) :**
    
    - `dog_bark()` (Poupoune s'énerve)
        
    - `doorbell()` (Livraison Amazon)
        
    - `coughing_fit()` (Quinte de toux de 10 secondes)
        
    - `tv_background()` (Augmenter le volume de la télé "BFMTV")
        

---

## 4.3 Guide d'Implémentation Technique (LangChain)

Voici la structure de code attendue pour valider les compétences :

### A. Configuration du Prompt Système (Victime)

Le prompt doit être modulaire.

Plaintext

```
Role: Vous êtes Jean Dubois... [Détails Persona]
Current Context: {dynamic_context_from_director}
Audience Event: {current_audience_constraint}
Available Tools: Vous POUVEZ utiliser les outils audios si la situation s'y prête.
```

### B. Gestion des Outils (MCP/Tools)

Utilisez le décorateur `@tool` de LangChain.

Python

```
from langchain.agents import tool

@tool
def play_dog_bark():
    """Joue un bruit d'aboiement de chien. À utiliser quand l'interlocuteur est pressant."""
    return "[SOUND_EFFECT: DOG_BARKING]"

@tool
def play_cough():
    """Simule une quinte de toux du vieux monsieur."""
    return "[SOUND_EFFECT: COUGHING]"
```

### C. La Boucle d'Exécution (Pseudo-code)

Python

```
# Initialisation
history = ConversationBufferMemory()
current_objective = "Répondre poliment mais lentement."

while simulation_active:
    # 1. L'arnaqueur (Humain ou autre LLM) parle
    user_input = get_scammer_input()
    
    # 2. Le Directeur analyse et met à jour l'objectif
    current_objective = director_llm.predict(f"Analyse: {user_input}. Script: TechSupport. Nouvel objectif ?")
    
    # 3. Check Audience (tous les X tours)
    if time_for_audience_vote:
        choices = audience_moderator.generate_choices()
        winner = run_vote(choices)
        audience_constraint = winner # ex: "Faire croire que le four brûle"
    
    # 4. La Victime répond (avec accès aux Tools Bruits)
    response = victim_agent.run(
        input=user_input, 
        objective=current_objective, 
        constraint=audience_constraint
    )
    
    # 5. Rendu
    print(f"Jean: {response}")
    if "[SOUND_EFFECT]" in response:
        play_audio_file(...)
```

---

## 4.4 Critères d'Évaluation Finaux

1. **Qualité du Repository :** `.gitignore` présent, `README.md` complet avec noms, code propre.
    
2. **Prompt Engineering :** La résistance de Jean Dubois (est-ce qu'il craque et donne le mot de passe ? Si oui, c'est raté).
    
3. **Complexité LangChain :** Utilisation correcte des _Agents_, _Tools_, et _Chains_.
    
4. **Orchestration Multi-LLM :** Le _Directeur_ change-t-il bien la stratégie en fonction du script ?
    
5. **Facteur "Fun" :** L'intégration des bruits et des votes audience fonctionne-t-elle ?

6. **Screenshots et exemples** : Ajouter des exemples qui montre que votre projet fonctionne.