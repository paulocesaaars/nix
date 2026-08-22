Webservice gratuito de alto desempenho para consulta de Código de Endereçamento Postal (CEP) do Brasil.

## Acessando o webservice de CEP

Para acessar o webservice, um CEP no formato de **{8}** dígitos deve ser fornecido, exemplo: "01001000".  
Após o CEP, deve ser fornecido o tipo de retorno desejado, que deve ser "json" ou "xml".

Exemplo de consulta de CEP:  
[viacep.com.br/ws/01001000/json/](https://viacep.com.br/ws/01001000/json/)

## Validação do CEP

Quando consultado um CEP de formato inválido, exemplo: "950100100" (9 dígitos), "95010A10" (alfanumérico), "95010 10" (espaço), o código de retorno da consulta será um **400** (Bad Request). Antes de acessar o webservice, valide o formato do CEP e certifique-se que o mesmo possua **{8}** dígitos. Exemplo de como validar o formato do CEP em javascript está disponível nos exemplos abaixo.

Quando consultado um CEP de formato válido, porém inexistente, por exemplo: "99999999", o retorno conterá um valor de "**erro**" igual a "**true**". Isso significa que o CEP consultado não foi encontrado na base de dados. Veja como tratar este "erro" em javascript nos exemplos abaixo.

## Formatos de Retorno

Veja exemplos de acesso ao webservice e os diferentes tipos de retorno:

#### JSON

URL: [viacep.com.br/ws/01001000/json/](https://viacep.com.br/ws/01001000/json/)

```

    {
      "cep": "01001-000",
      "logradouro": "Praça da Sé",
      "complemento": "lado ímpar",
      "unidade": "",
      "bairro": "Sé",
      "localidade": "São Paulo",
      "uf": "SP",
      "estado": "São Paulo",
      "regiao": "Sudeste",
      "ibge": "3550308",
      "gia": "1004",
      "ddd": "11",
      "siafi": "7107"
    }
            
```

#### JSONP

URL: [viacep.com.br/ws/01001000/json/?callback=callback_name](https://viacep.com.br/ws/01001000/json/?callback=callback_name)

```

    callback_name({
      "cep": "01001-000",
      "logradouro": "Praça da Sé",
      "complemento": "lado ímpar",
      "unidade": "",
      "bairro": "Sé",
      "localidade": "São Paulo",
      "uf": "SP",
      "estado": "São Paulo",
      "regiao": "Sudeste",
      "ibge": "3550308",
      "gia": "1004",
      "ddd": "11",
      "siafi": "7107"
    });
            
```

#### XML

URL: [viacep.com.br/ws/01001000/xml/](https://viacep.com.br/ws/01001000/xml/)

```

    <?xml version="1.0" encoding="UTF-8"?>
    <xmlcep>
        <cep>01001-000</cep>
        <logradouro>Praça da Sé</logradouro>
        <complemento>lado ímpar</complemento>
        <unidade></unidade>
        <bairro>Sé</bairro>
        <localidade>São Paulo</localidade>
        <uf>SP</uf>
        <estado>São Paulo</estado>
        <regiao>Sudeste</regiao>
        <ibge>3550308</ibge>
        <gia>1004</gia>
        <ddd>11</ddd>
        <siafi>7107</siafi>
    </xmlcep>
            
```

Origem IBGE: [Acessar Site](http://www.cidades.ibge.gov.br/)  
Origem GIA/ICMS (somente SP): [Visualizar PDF (Pág.137)](https://portal.fazenda.sp.gov.br/servicos/gia/Downloads/pre_formatado_ngia_v0210_gia0801.pdf)  
Origem DDD: [Acessar Site](https://informacoes.anatel.gov.br/legislacao/resolucoes/2022/1641-resolucao-749)  
Origem SIAFI: [Acessar Site](http://www.tesourotransparente.gov.br/ckan/dataset/lista-de-municipios-do-siafi)

## Exemplos: Auto Preenchimento de Endereço via CEP

#### Exemplo usando jQuery

Exemplo de acesso ao webservice utilizando jQuery.  
[Preenchimento de endereço via CEP com jQuery](https://viacep.com.br/exemplo/jquery/)

#### Exemplo em Javascript

Exemplo de acesso ao webservice com Javascript.  
[Preenchimento de endereço via CEP com Javascript](https://viacep.com.br/exemplo/javascript/)

## Pesquisa de CEP

Existem necessidades, por exemplo um cadastramento online onde o cliente desconhece o CEP da sua rua e será necessário realizar uma pesquisa para verificar a existência de um CEP que corresponda ao endereço. Para consultar um CEP na base de dados são necessários três parâmetros obrigatórios (UF, Cidade e Logradouro), sendo que para Cidade e Logradouro também é obrigatório um número mínimo de três caracteres a fim de evitar resultados extremamente abrangentes.

Identico a consulta por CEP, na pesquisa por endereço também é necessário informar o formato do retorno que deve ser "json" ou "xml". O resultado será ordenado pela proximidade do nome do logradouro e possui limite máximo de 50 (cinquenta) CEPs. Desta forma, quanto mais específico os parâmentros de entrada maior será a precisão do resultado.

Exemplos de pesquisa por endereço:  
[viacep.com.br/ws/RS/Porto Alegre/Domingos/json/](https://viacep.com.br/ws/RS/Porto%20Alegre/Domingos/json/)  
[viacep.com.br/ws/RS/Porto Alegre/Domingos Jose/json/](https://viacep.com.br/ws/RS/Porto%20Alegre/Domingos%20Jos%C3%A9/json/)  
[viacep.com.br/ws/RS/Porto Alegre/Domingos+Jose/json/](https://viacep.com.br/ws/RS/Porto%20Alegre/Domingos+Jos%C3%A9/json/)

Os exemplos acima demonstram diferentes formar de pesquisar pelas ocorrências "Domingos" e "José" na cidade de "Porto Algre/RS". Quando o nome da cidade ou do logradouro não contiver ao menos três caracteres o código de retorno será um **400** (Bad Request).

## Encontrou um CEP desatualizado?

Acesse o formulário abaixo para atualizar online.  
[Atualizar CEP](https://viacep.com.br/cep/)

## Módulos e Pacotes disponibilizados por Colaboradores

Precisando integrar sua linguagem de programação com o ViaCEP?  
Verifique a existência de módulos ou pacotes para facilitar seu processo.