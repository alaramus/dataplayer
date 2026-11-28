# Kubernetes

Ein Kubernetes-Cluster, erreicht über seinen API-Server: jeder Cluster — Ihr
eigener, k3s, kind oder einer, den eine Cloud betreibt. Sie sehen seine
Namespaces und jede Objektart, die er bereitstellt, eigene eingeschlossen, als
die Tabellen des Clusters selbst, was der Cluster über jedes Objekt sagt, die
Logs eines Pods und die Berichte des Clusters. Wie Verbindungen allgemein
funktionieren, steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Namespaces und jede Objektart darin, gruppiert wie in kubectl
- Arten außerhalb von Namespaces: Knoten, Volumes, Klassen und mehr
- Eigene Ressourcen, gefunden wie die eingebauten Arten
- Die Objekte einer Art als Tabelle wie bei `kubectl get`, sortierbar
- Die Übersicht eines Objekts: Zustand, Metadaten, Bedingungen, Inhalt
- Ein Objekt als YAML oder als JSON-Baum
- Die Ereignisse eines Objekts und die Pods, die ein Workload auswählt
- Die Logs eines Containers, neueste zuerst
- Der Cluster: Version, Knoten, Pods nach Phase, Ereignisse, API-Ressourcen

## Verbinden

**Anmelden mit** legt fest, wie sich DataPlayer am Cluster anmeldet:

- **Eine kubeconfig**: Fügen Sie die Datei ein oder lesen Sie sie mit der
  Schaltfläche neben dem Feld von der Festplatte. Zertifikate und Schlüssel
  müssen darin stehen, nicht als Dateien genannt sein;
  `kubectl config view --minify --flatten` schreibt eine solche. **Kontext**
  nennt den zu verwendenden Kontext; leer heißt der aktuelle der Datei.
- **Ein Token**: die `https://`-Adresse des **API-Servers**, sein
  **CA-Zertifikat** und ein Bearer-**Token**, etwa das eines Service-Accounts.
- **Ein Client-Zertifikat**: der API-Server, seine CA sowie ein
  **Client-Zertifikat** und ein **Client-Schlüssel**, die der Cluster annimmt.
  Der Schlüssel darf nicht verschlüsselt sein.

Lassen Sie **CA-Zertifikat** nur leer, wenn eine öffentliche Stelle das
Zertifikat des Servers signiert hat. Lassen Sie **Namespace** leer, um jeden zu
sehen, den Sie auflisten dürfen; nennen Sie einen, wenn Ihr Konto nur dort
arbeiten darf.

Manche kubeconfigs werden abgelehnt, jede mit ihrem Grund:

- eine, die sich anmeldet, indem sie ein Programm ausführt —
  `gke-gcloud-auth-plugin`, `aws`, `kubelogin` und ähnliche: DataPlayer führt
  auf seinem Server nichts aus;
- eine, die Dateien nennt, statt deren Daten zu enthalten;
- eine, die die Prüfung des Serverzertifikats abschaltet;
- eine, die sich mit Benutzername und Passwort anmeldet, was Kubernetes
  entfernt hat.

Wählen Sie einen **SSH-Tunnel** nur, wenn der API-Server nur aus einem anderen
Netz erreichbar ist. Der Cluster muss Kubernetes 1.27 oder neuer ausführen.

## Der Katalog

- **Cluster** enthält die Berichte des Clusters, siehe unten.
- **Namespaces** listet jeden Namespace auf, zuerst **Alle Namespaces**, das
  jede Art über alle hinweg mit einer Spalte **Namespace** zeigt.
- In einem Namespace sind seine Arten gruppiert: **Workloads**,
  **Netzwerk**, **Konfiguration**, **Speicher** und **Sonstige**. Sonstige
  enthält jede Art, die der Cluster bereitstellt und die nicht zu den
  bekannten gehört, eigene Ressourcen eingeschlossen, jede mit ihrer API-Gruppe.
- **Cluster-Ressourcen** enthält die Arten außerhalb von Namespaces, ebenso
  gruppiert, mit **Cluster** für Knoten, Namespaces und Definitionen.
- Eine Art öffnet sich als Tabelle mit den Spalten, die `kubectl get` für sie
  zeigt, und **Created** statt des Alters, damit sie sortiert. Jedes Objekt im
  Katalog zeigt neben seinem Namen seine ersten Spalten, etwa
  `1/1 · Running`. Mehr als zehntausend einer Art werden nicht aufgelistet.

## Wie sich ein Objekt öffnet

- Klicken Sie auf ein Objekt, um seine Übersicht zu öffnen: Art, Namespace,
  Erstellung, Besitzer und Zustand, dann das, wofür man diese Art liest —
  Knoten, Adressen und Container eines Pods mit Images, Zuständen und
  Neustarts; gewünschte, bereite und aktuelle Replikate eines Deployments;
  Typ, Adressen und Ports eines Service; Versionen und Kapazität eines
  Knotens; Klasse und Größe eines Volume-Claims — dann Bedingungen, Labels und
  Annotationen.
- Der Kopf der Übersicht öffnet das Objekt **Als YAML** oder **Als JSON** in
  einem eigenen Tab. Die Felder, in denen Kubernetes festhält, wer was
  geändert hat, bleiben weg.
- Seine Seiten öffnen sich als Tabellen in eigenen Tabs: **Ereignisse** dazu;
  die **Pods**, die ein Deployment, ein StatefulSet, ein DaemonSet, ein
  ReplicaSet, ein Job oder ein Service auswählt; und die **Logs** eines Pods,
  eine Seite je Container: Zeit und Text, neueste zuerst, bis zu zehntausend
  Zeilen, jede bei 16 KB abgeschnitten.
- **Die Werte eines Secrets werden nie gezeigt.** Seine Übersicht nennt seine
  Schlüssel und ihre Größe, und sein YAML und JSON zeigen statt jedes Werts
  eine Größe.

## Der Abschnitt Cluster

- **Überblick**: Version, Server, Kontext, wer Sie für den Cluster sind,
  bereite Knoten, Plattformen und die Zahl der Namespaces und der Pods in
  jeder Phase.
- **Knoten**: Status, Rollen, Versionen, Adresse, Betriebssystem, Laufzeit,
  Kapazität, Zuteilbares und Taints jedes Knotens.
- **Ereignisse**: was der Cluster zuletzt aufgezeichnet hat, neueste zuerst.
- **API-Ressourcen**: jede Art, die der Cluster bereitstellt, mit Gruppe,
  Version, Geltungsbereich und Verben.

## Wenn etwas abgelehnt wird

- Ein unerreichbarer API-Server, ein nicht vertrauenswürdiges Zertifikat oder
  ein nicht angenommenes Token oder Zertifikat stoppt die ganze Verbindung, und
  jede Ansicht sagt warum.
- Die Zugriffsregeln des Clusters können eine einzelne Anfrage ablehnen. Das
  heißt dann **Der Cluster erlaubt dieser Verbindung** mit dem, was gefragt
  wurde, etwa `list secrets`; der Rest des Clusters bleibt lesbar.

## Was Kubernetes hier noch nicht hat

- Objekte ändern: skalieren, neu starten, löschen, als YAML bearbeiten
- Einen Knoten leeren, ein Terminal im Container, mitlaufende Logs
- Metriken auf einem Dashboard, Suche, eine Datenbank im Cluster öffnen
- Anmeldung an Google Kubernetes Engine mit einem Google-Cloud-Konto
