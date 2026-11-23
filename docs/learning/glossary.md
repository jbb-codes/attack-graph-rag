# Glossary

Plain-English keywords for a Node/TS developer new to Python, RDF, and SPARQL. One line each. New terms are added as issues are implemented.

## ATT&CK data

- **ATT&CK:** MITRE's public catalog of attacker behavior.
- **Technique:** one attacker method, with an ID like `T1566` (phishing).
- **Group:** an attacker crew, like APT29 (`G0016`).
- **Software:** malware or tools attackers use (`S...`).
- **Mitigation:** a defense against a technique (`M...`).
- **Tactic:** the goal a technique serves, like `persistence`.
- **STIX:** the JSON format MITRE publishes ATT&CK in. It has objects plus "relationship" objects that link them.
- **Fixture:** a small fake dataset for tests, so they run fast and offline.

## Graph and queries

- **RDF:** a way to store facts as `subject - predicate - object` triples.
- **Triple:** one fact, like `T1566 - hasName - "Phishing"`.
- **Graph:** a pile of triples. Things link to other things.
- **SPARQL:** SQL for triples. You describe a pattern and it returns every match.
- **rdflib:** the Python library that holds the graph and runs SPARQL.
- **`initBindings`:** safely plugs values into a query, like a `?` placeholder in SQL.

## Tooling and testing

- **Seam:** the one place tests plug in. Later this will be `ask()`.
- **Exit code:** 0 means success, 1 means "not found", 2 means bad input.
- **stdout / stderr:** normal output vs error output.
- **Entry point:** a command name mapped to a function.
- **venv:** an isolated folder of packages for one project.
- **Lockfile:** an exact record of installed versions, so every machine gets the same ones.
