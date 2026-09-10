/* Dessin SVG adapte directement de apercugraphe.html fourni par l'utilisateur.
 * Les donnees et etats sont fournis par le moteur ; aucun scenario preenregistre. */

(function () {
  "use strict";

  var COL_LARGEUR = 224;
  var RAYON = 30;
  var ESPACE_V = 96;
  var MARGE_HAUT = 56;
  var MARGE_BAS = 54;

  /* De combien la prise recule par rapport au bord de la pastille. Assez pour
   * qu'on voie le corps de la prise, pas au point de detacher le cable. */
  var RECUL = 12;
  var DUREE = 700;

  function svgEl(nom, attrs) {
    var el = document.createElementNS("http://www.w3.org/2000/svg", nom);
    for (var cle in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, cle)) {
        el.setAttribute(cle, attrs[cle]);
      }
    }
    return el;
  }

  /* Pose les pastilles en colonnes et renvoie leurs centres.
   *
   * Les colonnes vides sont retirees AVANT le calcul : une stack sans client de
   * telechargement laissait sinon un vide au milieu du dessin, et les cables le
   * traversaient sans raison visible. */
  function disposer(plan) {
    var colonnes = plan.colonnes.filter(function (c) {
      return plan.noeuds.some(function (n) { return n.colonne === c; });
    });

    var positions = {};
    var hauteurMax = 60;

    colonnes.forEach(function (colonne) {
      var dedans = plan.noeuds.filter(function (n) { return n.colonne === colonne; });
      hauteurMax = Math.max(hauteurMax, dedans.length * ESPACE_V - (ESPACE_V - 2 * RAYON));
    });

    colonnes.forEach(function (colonne, index) {
      var dedans = plan.noeuds.filter(function (n) { return n.colonne === colonne; });
      var hauteur = dedans.length * ESPACE_V - (ESPACE_V - 2 * RAYON);
      /* Chaque colonne est centree verticalement : sans cela, une colonne a une
       * seule pastille restait collee en haut et les cables plongeaient. */
      var decalage = (hauteurMax - hauteur) / 2;
      dedans.forEach(function (noeud, rang) {
        positions[noeud.id] = {
          cx: index * COL_LARGEUR + RAYON + 30,
          cy: MARGE_HAUT + decalage + RAYON + rang * ESPACE_V,
          noeud: noeud
        };
      });
    });

    return {
      colonnes: colonnes,
      positions: positions,
      largeur: Math.max(220, (colonnes.length - 1) * COL_LARGEUR + 2 * RAYON + 100),
      hauteur: MARGE_HAUT + hauteurMax + MARGE_BAS
    };
  }

  /* Le trace d'un cable, de bord de pastille a bord de pastille.
   *
   * Il part et arrive HORIZONTALEMENT, ce qui donne aux prises un angle franc :
   * une prise de travers ne ressemble a rien. Le sens compte — `qui` remonte le
   * dessin de droite a gauche — et on sort alors par le bord oppose pour que le
   * cable contourne au lieu de traverser la pastille. */
  function courbe(depart, arrivee) {
    var versLaDroite = arrivee.cx > depart.cx;
    var sens = versLaDroite ? 1 : -1;
    var x1 = depart.cx + sens * (RAYON + RECUL);
    var y1 = depart.cy;
    var x2 = arrivee.cx - sens * (RAYON + RECUL);
    var y2 = arrivee.cy;
    var pousse = Math.max(52, Math.abs(x2 - x1) * 0.5) * sens;
    return {
      d: "M" + x1 + "," + y1 + " C" + (x1 + pousse) + "," + y1 +
         " " + (x2 - pousse) + "," + y2 + " " + x2 + "," + y2,
      depart: { x: x1, y: y1, angle: versLaDroite ? 0 : 180 },
      arrivee: { x: x2, y: y2, angle: versLaDroite ? 180 : 0 }
    };
  }

  /* Une prise : un corps et deux broches, dessines vers la gauche depuis le
   * point de branchement, puis pivotes. C'est la forme du logo, reduite. */
  function prise(point) {
    var groupe = svgEl("g", {
      "class": "prise",
      transform: "translate(" + point.x + "," + point.y + ") rotate(" + point.angle + ")"
    });
    groupe.appendChild(svgEl("rect", {
      x: -13, y: -9, width: 13, height: 18, rx: 3.5, "class": "corps"
    }));
    groupe.appendChild(svgEl("rect", { x: 0, y: -5.4, width: 7, height: 3, rx: 1.5 }));
    groupe.appendChild(svgEl("rect", { x: 0, y: 2.4, width: 7, height: 3, rx: 1.5 }));
    return groupe;
  }

  function degrade(id, stops) {
    var grad = svgEl("linearGradient", { id: id, x1: "0", y1: "0", x2: "1", y2: "0" });
    stops.forEach(function (stop) {
      grad.appendChild(svgEl("stop", {
        offset: (stop[0] * 100) + "%", "stop-color": stop[1]
      }));
    });
    return grad;
  }

  function dessiner(hote, plan, libelles, actions) {
    var mise = disposer(plan);
    var svg = svgEl("svg", {
      viewBox: "0 0 " + mise.largeur + " " + mise.hauteur,
      role: actions ? "group" : "img",
      "aria-label": libelles.graphe || "graphe"
    });

    /* Le degrade est declare UNE fois et partage par tous les cables. Un
     * degrade par cable multiplierait les noeuds sans rien changer a l'oeil. */
    var defs = svgEl("defs", {});
    defs.appendChild(degrade("cable", plan.cable || [[0, "#F79B45"], [1, "#8B36C9"]]));
    svg.appendChild(defs);

    var coucheCables = svgEl("g", {});
    var couchePrises = svgEl("g", {});
    var coucheNoeuds = svgEl("g", {});
    var coucheActions = svgEl("g", {});
    svg.appendChild(coucheCables);
    svg.appendChild(couchePrises);
    svg.appendChild(coucheActions);
    svg.appendChild(coucheNoeuds);

    mise.colonnes.forEach(function (colonne, index) {
      var titre = svgEl("text", {
        x: index * COL_LARGEUR + RAYON + 30,
        y: 22,
        "text-anchor": "middle",
        "class": "entete-colonne"
      });
      titre.textContent = (libelles.colonnes || {})[colonne] || colonne;
      svg.insertBefore(titre, coucheCables);
    });

    var cables = {};
    var permanents = [];
    var allCables = [];
    plan.liens.forEach(function (lien) {
      var depart = mise.positions[lien.source];
      var arrivee = mise.positions[lien.cible];
      if (!depart || !arrivee) { return; }
      var trace = courbe(depart, arrivee);

      var fantome = svgEl("path", { d: trace.d, "class": "fantome" });
      coucheCables.appendChild(fantome);
      var vivant = svgEl("path", { d: trace.d, "class": "vivant" });
      coucheCables.appendChild(vivant);
      var bille = svgEl("circle", { r: 4, "class": "bille" });
      coucheCables.appendChild(bille);

      /* Le flux : des tirets qui remontent le cable en boucle une fois celui-ci
       * branche. Il ne porte aucune information que le trait ne donne deja —
       * son role est de montrer qu'un lien est VIVANT et pas seulement etabli. */
      var flux = svgEl("path", { d: trace.d, "class": "flux" });
      coucheCables.appendChild(flux);

      var priseDepart = prise(trace.depart);
      var priseArrivee = prise(trace.arrivee);
      couchePrises.appendChild(priseDepart);
      couchePrises.appendChild(priseArrivee);

      var cable = {
        fantome: fantome,
        vivant: vivant,
        flux: flux,
        bille: bille,
        prises: [priseDepart, priseArrivee],
        lien: lien
      };

      if (actions && actions.lien) {
        cable.hit = svgEl("path", {d: trace.d, "class": "graph-hit", role: "button", tabindex: 0, "data-link": lien.id});
        activer(cable.hit, function() { actions.lien(lien.id); });
        coucheActions.appendChild(cable.hit);
      }
      allCables.push(cable);
      var titreCable = svgEl("title", {});
      titreCable.textContent = lien.description || lien.verbe || "";
      vivant.appendChild(titreCable);
      /* Un tunnel VPN nait branche : il est pose par le fichier compose, donc
       * vrai avant la premiere etape, et aucun evenement ne viendra l'allumer. */
      if (lien.permanent) {
        permanents.push(cable);
        return;
      }

      /* UNE etape peut porter PLUSIEURS cables : `seerr/setup` etablit a lui
       * seul les liens vers Jellyfin, Sonarr et Radarr. Indexer un cable par
       * etape en perdait donc deux sur trois. */
      if (!cables[lien.etape]) { cables[lien.etape] = []; }
      cables[lien.etape].push(cable);
    });

    var noeuds = {};
    plan.noeuds.forEach(function (noeud) {
      var pos = mise.positions[noeud.id];
      if (!pos) { return; }
      var groupe = svgEl("g", {
        "class": "noeud teinte-" + noeud.teinte, "data-service": noeud.id
      });
      groupe.appendChild(svgEl("circle", { cx: pos.cx, cy: pos.cy, r: RAYON, "class": "halo" }));
      groupe.appendChild(svgEl("circle", { cx: pos.cx, cy: pos.cy, r: RAYON, "class": "anneau" }));

      /* Le logo s'il a ete embarque, les deux lettres sinon. Le dossier des
       * logos peut etre vide — aucune licence libre n'accorde de droit de
       * marque — et le dessin doit tenir dans les deux cas. */
      if (noeud.logo) {
        var image = svgEl("image", {
          x: pos.cx - 21, y: pos.cy - 21, width: 42, height: 42,
          href: noeud.logo, "clip-path": "circle(21px)", "class": "logo"
        });
        /* `href` seul suffit en SVG 2, mais Safari a longtemps exige la forme
         * XLink et l'ignore silencieusement sans elle : l'image ne s'affiche
         * pas, et rien ne le signale. Les deux coutent un attribut. */
        image.setAttributeNS("http://www.w3.org/1999/xlink", "href", noeud.logo);
        groupe.appendChild(image);
      } else {
        var pastille = svgEl("text", {
          x: pos.cx, y: pos.cy + 6, "text-anchor": "middle", "class": "pastille"
        });
        pastille.textContent = noeud.pastille;
        groupe.appendChild(pastille);
      }

      var nom = svgEl("text", {
        x: pos.cx, y: pos.cy + RAYON + 18, "text-anchor": "middle", "class": "nom"
      });
      nom.textContent = noeud.nom;
      groupe.appendChild(nom);

      var sous = svgEl("text", {
        x: pos.cx, y: pos.cy + RAYON + 31, "text-anchor": "middle", "class": "sous"
      });
      groupe.appendChild(sous);

      var titreNoeud = svgEl("title", {});
      groupe.appendChild(titreNoeud);
      if (actions && actions.noeud) {
        groupe.setAttribute("role", "button"); groupe.setAttribute("tabindex", "0");
        activer(groupe, function() { actions.noeud(noeud.id); });
      }
      coucheNoeuds.appendChild(groupe);
      noeuds[noeud.id] = { groupe: groupe, sous: sous, titre: titreNoeud };
    });

    hote.innerHTML = "";
    hote.appendChild(svg);
    return { cables: cables, permanents: permanents, noeuds: noeuds, allCables: allCables };
  }

  /* Branche le cable : le trait se tire de la source vers la cible, une bille le
   * remonte, et la prise d'arrivee s'enclenche quand elle arrive.
   *
   * `stroke-dashoffset` ne s'anime que si la longueur est connue : on la mesure
   * sur le trace reel plutot que de l'estimer, sinon le trait saute a la fin. */
  function brancher(cable, ok) {
    var longueur = cable.vivant.getTotalLength();
    cable.vivant.style.setProperty("--longueur", longueur);
    if (!ok) { cable.vivant.classList.add("echoue"); }
    /* Un reflow force AVANT d'ajouter la classe : sans lui, le navigateur voit
     * la longueur et l'offset final dans le meme lot et n'anime rien. */
    void cable.vivant.getBoundingClientRect();
    cable.vivant.classList.add("tire");
    cable.prises[0].classList.add(ok ? "branchee" : "echouee");

    /* L'ETAT FINAL est pose par un minuteur, JAMAIS par requestAnimationFrame.
     *
     * Un onglet qui n'est pas au premier plan ne recoit plus de frames. La
     * bille s'arretait alors en chemin et, comme tout l'etat d'arrivee pendait a
     * la fin de sa course, la prise d'arrivee et le flux n'arrivaient jamais —
     * definitivement. Constate en ouvrant la page : 31 cables sur 35 tires,
     * mais leur prise d'arrivee eteinte et aucun flux, bien apres la fin.
     *
     * Un `setTimeout` est ralenti en arriere-plan, mais il FINIT par se
     * declencher. Le mouvement est cosmetique ; l'etat ne doit pas en dependre. */
    window.setTimeout(function () {
      if (cable.state !== "fait" || !cable.vivant.isConnected) { return; }
      cable.bille.classList.remove("court");
      /* La prise d'arrivee ne s'allume qu'ICI, une fois le cable parcouru :
       * c'est ce decalage qui fait lire « ca vient de se brancher » plutot que
       * « c'est branche depuis toujours ». */
      cable.prises[1].classList.add(ok ? "branchee" : "echouee");
      /* Et le flux part dans la foulee : un lien etabli est un lien qui
       * travaille. Un lien en echec ne coule pas. */
      if (ok) { cable.flux.classList.add("coule"); }
    }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : DUREE);

    /* La bille, elle, est purement decorative : si les frames manquent, elle
     * n'avance pas, et ce n'est pas grave. */
    var bille = cable.bille;
    var debut = null;
    bille.classList.add("court");
    function pas(horodatage) {
      if (cable.state !== "fait" || !cable.vivant.isConnected) { return; }
      if (debut === null) { debut = horodatage; }
      var avance = Math.min(1, (horodatage - debut) / DUREE);
      var point = cable.vivant.getPointAtLength(longueur * avance);
      bille.setAttribute("cx", point.x);
      bille.setAttribute("cy", point.y);
      if (avance < 1) { requestAnimationFrame(pas); }
    }
    requestAnimationFrame(pas);
  }

  function etatEtape(id, snapshot) {
    var result = (snapshot.graph_results || {})[id];
    if (result) { return !result.ok ? "echoue" : (result.warnings || []).length ? "avertissement" : "fait"; }
    return snapshot.active_step === id && snapshot.status === "running" ? "actif" : "prevu";
  }

  function activer(element, callback) {
    element.addEventListener("click", callback);
    element.addEventListener("keydown", function(event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); callback(); }
    });
  }

  function Vue(hote, compte, barre, liste, actions) {
    var dessin = null, plan = null, labels = {}, lang = null;
    this.appliquer = function(snapshot, icons, libelles, language) {
      var next = snapshot.graph;
      if (!next) { return; }
      labels = libelles;
      var fresh = !plan || next.id !== plan.id || language !== lang;
      if (fresh) {
        plan = next; lang = language;
        var withIcons = Object.assign({}, plan, {noeuds: plan.noeuds.map(function(n) {
          return Object.assign({}, n, {logo: icons[n.id] || ""});
        })});
        dessin = dessiner(hote, withIcons, labels, actions);
      }
      var results = snapshot.graph_results || {};
      dessin.allCables.forEach(function(cable) {
        var lien = cable.lien;
        var state = (snapshot.link_states || {})[lien.id] || (lien.structure ? (snapshot.deployed ? "configure" : "prevu") : etatEtape(lien.etape, snapshot));
        var changed = state !== cable.state;
        cable.fantome.classList.toggle("actif", state === "actif");
        if (changed) {
          cable.state = state;
          cable.vivant.classList.remove("tire", "echoue", "avertissement", "structure");
          cable.flux.classList.remove("coule");
          cable.bille.classList.remove("court");
          cable.prises.forEach(function(p) { p.classList.remove("branchee", "echouee", "structure"); });
          if (state === "fait" || state === "echoue" || state === "avertissement") {
            if (fresh || state !== "fait") {
              cable.vivant.style.setProperty("--longueur", cable.vivant.getTotalLength());
              cable.vivant.classList.add("tire");
              cable.prises.forEach(function(p) { p.classList.add(state === "echoue" ? "echouee" : "branchee"); });
              if(state === "fait") { cable.flux.classList.add("coule"); }
            } else { brancher(cable, true); }
            if(state !== "fait") { cable.vivant.classList.add(state); }
          } else if (state === "configure") {
            cable.vivant.classList.add("structure");
            cable.prises.forEach(function(p) { p.classList.add("structure"); });
          }
        }
        var cableText = lien.verbe + " — " + (labels.liens || labels)[state] + ". " + lien.description;
        cable.vivant.querySelector("title").textContent = cableText;
        if(cable.hit) { cable.hit.setAttribute("aria-label", cableText); }
      });
      var descriptions = [];
      plan.noeuds.forEach(function(node) {
        var required = new Set(node.reglages);
        var structural = false;
        plan.liens.forEach(function(lien) {
          if(lien.source !== node.id && lien.cible !== node.id) { return; }
          if(lien.structure) { structural = true; } else { required.add(lien.etape); }
        });
        var states = Array.from(required).map(function(id) { return etatEtape(id, snapshot); });
        var state = states.includes("echoue") ? "echoue" : states.includes("avertissement") ? "avertissement" : states.includes("actif") ? "actif" :
          states.length && states.every(function(s) { return s === "fait"; }) ? "fait" :
          !states.length && snapshot.deployed ? "configure" : "prevu";
        if (state === "fait" && structural && !snapshot.deployed) { state = "prevu"; }
        state = (snapshot.node_states || {})[node.id] || state;
        var nodeLabel = (snapshot.node_details || {})[node.id] || (labels.noeuds || labels)[state];
        var el = dessin.noeuds[node.id];
        ["fait","actif","echoue","avertissement","configure","prevu","arrete","inconnu"].forEach(function(s) { el.groupe.classList.toggle(s, s === state); });
        el.sous.textContent = snapshot.node_states || state === "echoue" || state === "avertissement" ? nodeLabel : "";
        el.titre.textContent = node.nom + " — " + nodeLabel;
        if(actions) { el.groupe.setAttribute("aria-label", el.titre.textContent); }
        descriptions.push(node.nom + " : " + nodeLabel);
      });
      var done = plan.etapes.filter(function(id) { return !!results[id]; }).length;
      compte.textContent = done + " / " + plan.etapes.length + " " + labels.etapes;
      barre.max = Math.max(1, plan.etapes.length); barre.value = done;
      // Liste equivalente, lisible sans SVG et sans devoir distinguer les couleurs.
      liste.replaceChildren.apply(liste, descriptions.map(function(description) {
        var li = document.createElement("li"); li.textContent = description; return li;
      }));
    };
    this.selectionner = function(nodeId, edgeId) {
      if(!dessin) { return; }
      var edge = plan.liens.find(function(e) { return e.id === edgeId; });
      var related = new Set(edge ? [edge.source, edge.cible] : nodeId ? [nodeId] : []);
      if(nodeId) { plan.liens.forEach(function(e) { if(e.source === nodeId || e.cible === nodeId) { related.add(e.source); related.add(e.cible); } }); }
      Object.keys(dessin.noeuds).forEach(function(id) {
        var el = dessin.noeuds[id].groupe;
        el.classList.toggle("dimmed", related.size > 0 && !related.has(id));
        el.classList.toggle("selected", id === nodeId);
        el.setAttribute("aria-pressed", String(id === nodeId));
      });
      dessin.allCables.forEach(function(cable) {
        var active = cable.lien.id === edgeId;
        var dim = !!edgeId && !active || !!nodeId && cable.lien.source !== nodeId && cable.lien.cible !== nodeId;
        [cable.fantome, cable.vivant, cable.flux, cable.bille].concat(cable.prises).forEach(function(el) { el.classList.toggle("dimmed", dim); });
        if(cable.hit) { cable.hit.setAttribute("aria-pressed", String(active)); }
      });
    };
  }
  window.PlugArrGraphe = { Vue: Vue, disposer: disposer, courbe: courbe };
})();
