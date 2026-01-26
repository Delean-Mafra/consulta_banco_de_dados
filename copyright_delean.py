
# Biblioteca de Direitos Autorais - Delean Mafra
# Imprime automaticamente o copyright com o ano atual


from datetime import datetime


def copyright_delean():
    
    # Imprime a mensagem de copyright com o ano atual.
    # O ano é obtido automaticamente do sistema.
    
    ano_atual = datetime.now().year
    autor = f"Copyright ©{ano_atual} | Delean Mafra, todos os direitos reservados."
    print(autor)
    return autor

  