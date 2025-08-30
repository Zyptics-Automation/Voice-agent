# knowledge.py

def get_knowledge_base():
    """
    Returns the company's information as a formatted string for the LLM's system prompt.
    This acts as the agent's knowledge base.
    """
    return """
    - About Us: Zyptics is a team of AI experts building custom automation solutions. Our mission is to deliver measurable ROI within 90 days.
    - Services: We offer AI Chatbots, Automated Ticket Routing, and Voice Response Systems.
    - Getting Started: New subscribers receive a secure account activation link via email. Dashboard setup takes 2-7 business days.
    - Subscriptions: We offer Starter, Growth, and Business plans. Users can upgrade or downgrade anytime.
    - Contact: Human support is available via email at info@zyptics.com or through live chat on our website during business hours (9am-6pm CET, Mon-Fri).
    - Payments: We accept major credit/debit cards, crypto, and ACH payments via Stripe.
    - Data Security: We are GDPR compliant and use enterprise-grade encryption. We never sell or share user data.
    """