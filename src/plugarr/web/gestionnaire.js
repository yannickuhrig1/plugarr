'use strict';
// Gestionnaire d'installations PlugArr. Les textes viennent du serveur
// (/api/textes), traduits cote Python : aucun libelle n'est ecrit ici.
(() => {
  const $ = id => document.getElementById(id);
  let jeton = new URLSearchParams(location.hash.slice(1)).get('jeton');
  if (jeton) {
    sessionStorage.setItem('plugarr-gestion', jeton);
    history.replaceState(null, '', location.pathname);
  } else {
    jeton = sessionStorage.getItem('plugarr-gestion');
  }

  // Un gestionnaire relance donne une nouvelle adresse a une fenetre deja
  // ouverte : on adopte son jeton au lieu d'afficher « session expiree ».
  window.addEventListener('hashchange', () => {
    const nouveau = new URLSearchParams(location.hash.slice(1)).get('jeton');
    if (!nouveau) return;
    jeton = nouveau;
    sessionStorage.setItem('plugarr-gestion', jeton);
    history.replaceState(null, '', location.pathname);
    dernier = '';
    erreur('');
    rafraichir();
  });

  let T = {};
  let dernier = '';
  let etat = null;
  const ouverts = new Set();
  let rafraichisseur = null;
  let ferme = false;

  const CLASSES = {
    'en-marche': 'ok', partielle: 'attention', arretee: '', 'docker-absent': 'alerte',
    introuvable: 'alerte', illisible: 'alerte', 'version-future': 'alerte',
    deconnectee: '', injoignable: 'alerte', verification: '', 'autre-dossier': 'attention'
  };

  async function api(chemin, corps) {
    const options = {headers: {Authorization: 'Bearer ' + (jeton || '')}};
    if (corps !== undefined) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(corps);
    }
    let reponse;
    try {
      reponse = await fetch(chemin, options);
    } catch (e) {
      throw new Error(T.erreurReseau || 'PlugArr ne repond plus.');
    }
    const donnees = await reponse.json().catch(() => ({}));
    if (!reponse.ok) throw new Error(donnees.erreur || ('HTTP ' + reponse.status));
    return donnees;
  }

  function fmt(modele, valeurs) {
    return String(modele || '').replace(/\{(\w+)\}/g, (m, k) => (k in valeurs ? String(valeurs[k]) : m));
  }

  function el(tag, attrs, ...enfants) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v === null || v === undefined) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const e of enfants) if (e !== null && e !== undefined && e !== false) n.append(e);
    return n;
  }

  function bouton(texte, action, classe) {
    return el('button', {type: 'button', class: classe || 'secondary', text: texte, onclick: action});
  }

  function erreur(message) {
    const zone = $('erreur');
    zone.textContent = message || '';
    zone.hidden = !message;
  }

  function info(message) {
    const zone = $('info');
    zone.textContent = message || '';
    zone.hidden = !message;
  }

  // -- dialogue ---------------------------------------------------------------

  let tour = 0;

  // Chaque ouverture porte un numero : une action qui a remplace le contenu
  // (le journal d'une tache, par exemple) ne doit pas etre fermee par celle
  // qui l'a lancee.
  function dialogue(titre, contenu, actions) {
    const d = $('dialogue');
    $('dialogue-titre').textContent = titre;
    $('dialogue-contenu').replaceChildren(...contenu);
    $('dialogue-actions').replaceChildren(...actions);
    if (!d.open) d.showModal();
    tour += 1;
    return tour;
  }

  function fermerDialogue() {
    const d = $('dialogue');
    if (d.open) d.close();
  }

  function confirmer(titre, texte, libelle, action) {
    let numero = 0;
    const ok = bouton(libelle || T.confirmer, async () => {
      ok.disabled = true;
      try {
        await action();
        if (tour === numero) fermerDialogue();
      } catch (e) {
        if (tour !== numero) {
          fermerDialogue();
          erreur(e.message);
          return;
        }
        ok.disabled = false;
        $('dialogue-contenu').append(el('p', {class: 'notice error', text: e.message}));
      }
    }, 'primary');
    numero = dialogue(titre, [el('p', {text: texte})], [bouton(T.annuler, fermerDialogue), ok]);
    ok.focus();
  }

  // -- taches -----------------------------------------------------------------

  async function suivreTache(id, titre) {
    const journal = el('pre', {class: 'journal', 'aria-live': 'polite'});
    const statut = el('p', {class: 'muted'});
    dialogue(titre, [statut, journal], [bouton(T.fermer, fermerDialogue, 'primary')]);
    while ($('dialogue').open) {
      let tache;
      try {
        tache = await api('/api/taches/' + encodeURIComponent(id));
      } catch (e) {
        statut.textContent = e.message;
        return null;
      }
      const enBas = journal.scrollTop + journal.clientHeight >= journal.scrollHeight - 20;
      journal.textContent = tache.lignes.join('\n');
      if (enBas) journal.scrollTop = journal.scrollHeight;
      statut.textContent = T['tache-' + tache.statut] + (tache.message ? ' : ' + tache.message : '');
      if (tache.statut !== 'en-cours') {
        rafraichir();
        return tache;
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    return null;
  }

  async function lancer(instance, action, titre) {
    const reponse = await api('/api/instances/' + instance.id + '/' + action, {});
    rafraichir();
    return suivreTache(reponse.tache.id, titre + ' : ' + instance.nom);
  }

  // -- dialogues propres a une installation -----------------------------------

  function dialoguePack(instance) {
    const retenus = (instance.pack && instance.pack.retenus) || [];
    const ecartes = (instance.pack && instance.pack.ecartes) || [];
    const contenu = [el('p', {text: fmt(T.packIntro, {version: etat.version})})];
    if (retenus.length) {
      const corps = el('tbody', {}, ...retenus.map(e => el('tr', {},
        el('td', {text: e.nom}), el('td', {text: e.installee}), el('td', {text: e.catalogue}))));
      contenu.push(el('div', {class: 'table-defile'}, el('table', {class: 'pack'},
        el('thead', {}, el('tr', {}, el('th', {text: T.colService}), el('th', {text: T.colInstallee}),
          el('th', {text: T.colCatalogue}))), corps)));
    } else {
      contenu.push(el('p', {class: 'notice', text: T.rienAFaire}));
    }
    if (ecartes.length) {
      contenu.push(el('p', {class: 'muted', text: T.ecartes}));
      contenu.push(el('ul', {class: 'ecartes'}, ...ecartes.map(r => el('li', {text: r}))));
    }
    const actions = [bouton(T.annuler, fermerDialogue)];
    if (retenus.length) {
      actions.push(bouton(T.appliquer, async () => {
        try {
          await lancer(instance, 'pack', T.pack);
        } catch (e) {
          fermerDialogue();
          erreur(e.message);
        }
      }, 'primary'));
    }
    dialogue(T.packTitre + ' : ' + instance.nom, contenu, actions);
  }

  function dialogueConnexion(instance, message) {
    const champs = {};
    const lire = (id, libelle, type) => {
      champs[id] = el('input', {id: 'cnx-' + id, type: type || 'password', autocomplete: 'off'});
      return el('label', {for: 'cnx-' + id}, el('span', {text: libelle}), champs[id]);
    };
    const fichier = el('input', {id: 'cnx-cle', type: 'file'});
    const souvenir = el('input', {id: 'cnx-souvenir', type: 'checkbox'});
    const contenu = [
      el('p', {text: T.connexionIntro}),
      el('p', {}, el('span', {class: 'muted', text: T.empreinte + ' : '}), el('code', {text: instance.empreinte || '-'})),
      lire('password', T.motDePasse),
      el('label', {for: 'cnx-cle'}, el('span', {text: T.clePrivee}), fichier),
      lire('passphrase', T.phraseDePasse),
      lire('sudo_password', T.sudo),
    ];
    if (instance.coffre) contenu.push(el('label', {class: 'coche', for: 'cnx-souvenir'}, souvenir, el('span', {text: T.seSouvenir})));
    if (message) contenu.push(el('p', {class: 'notice error', text: message}));
    const ok = bouton(T.connexion, async () => {
      ok.disabled = true;
      const corps = {se_souvenir: souvenir.checked};
      for (const [cle, champ] of Object.entries(champs)) if (champ.value) corps[cle] = champ.value;
      try {
        if (fichier.files && fichier.files[0]) corps.private_key = await fichier.files[0].text();
        await api('/api/instances/' + instance.id + '/connexion', corps);
        fermerDialogue();
        rafraichir();
      } catch (e) {
        dialogueConnexion(instance, e.message);
      }
    }, 'primary');
    dialogue(fmt(T.connexionTitre, {nom: instance.nom}), contenu, [bouton(T.annuler, fermerDialogue), ok]);
    champs.password.focus();
  }

  async function seConnecter(instance) {
    if (instance.secret_garde) {
      try {
        await api('/api/instances/' + instance.id + '/connexion', {});
        rafraichir();
        return;
      } catch (e) {
        dialogueConnexion(instance, e.message);
        return;
      }
    }
    dialogueConnexion(instance);
  }

  function dialogueRenommer(instance) {
    const champ = el('input', {id: 'renommer-nom', type: 'text', value: instance.nom, maxlength: '60'});
    const ok = bouton(T.enregistrer, async () => {
      try {
        await api('/api/instances/' + instance.id + '/renommer', {nom: champ.value});
        fermerDialogue();
        rafraichir();
      } catch (e) {
        erreur(e.message);
        fermerDialogue();
      }
    }, 'primary');
    dialogue(T.renommer, [el('label', {for: 'renommer-nom'}, el('span', {text: T.renommerTitre}), champ)],
      [bouton(T.annuler, fermerDialogue), ok]);
    champ.select();
  }

  // -- rendu ------------------------------------------------------------------

  function simple(instance, route) {
    return async () => {
      erreur('');
      try {
        await api('/api/instances/' + instance.id + '/' + route, {});
        rafraichir();
      } catch (e) {
        erreur(e.message);
      }
    };
  }

  function carte(instance) {
    const etatNom = instance.etat || 'verification';
    const services = instance.services || [];
    const enMarche = services.filter(s => s.up).length;
    const retenus = (instance.pack && instance.pack.retenus) || [];
    const occupe = Boolean(instance.tache);

    const tete = el('div', {class: 'carte-tete'},
      el('div', {class: 'identite'},
        el('div', {class: 'nom'}, el('span', {text: instance.nom}),
          el('span', {class: 'chip', text: instance.type === 'ssh' ? T.ssh : T.local})),
        el('div', {class: 'lieu', text: instance.lieu})),
      el('span', {class: 'pastille ' + (CLASSES[etatNom] || ''), text: T['etat-' + etatNom] || etatNom}));

    const mesures = el('div', {class: 'mesures'});
    if (services.length) mesures.append(el('span', {}, el('strong', {text: fmt(T.services, {n: enMarche, total: services.length})})));
    if (instance.pack) {
      mesures.append(el('span', {}, retenus.length
        ? el('strong', {text: fmt(T.packEcarts, {n: retenus.length})})
        : el('span', {text: T.packAJour})));
    } else if (instance.type === 'ssh' && !instance.connecte) {
      mesures.append(el('span', {text: T.packInconnu}));
    }

    const actions = el('div', {class: 'actions-carte'});
    const menu = el('div', {class: 'plus-menu'});
    const vivante = !['introuvable', 'illisible', 'version-future'].includes(etatNom);
    const ajouterMenu = (texte, action, classe) => menu.append(el('button', {type: 'button', class: classe || '', text: texte, onclick: action}));

    if (instance.type === 'local') {
      if (etatNom === 'autre-dossier') {
        ajouterMenu(T.dossier, simple(instance, 'dossier'));
      } else if (vivante) {
        actions.append(bouton(T.console, simple(instance, 'console'), 'primary'));
        if (etatNom === 'en-marche' || etatNom === 'partielle') {
          actions.append(bouton(T.arreter, () => confirmer(T.arreter, fmt(T.confirmerArreter, {nom: instance.nom}), T.arreter,
            () => lancer(instance, 'arreter', T.arreter))));
        }
        if (etatNom !== 'en-marche') actions.append(bouton(T.demarrer, () => lancer(instance, 'demarrer', T.demarrer).catch(e => erreur(e.message))));
        if (instance.pack) actions.append(bouton(T.pack, () => dialoguePack(instance)));
        ajouterMenu(T.sauvegarder, () => lancer(instance, 'sauvegarder', T.sauvegarder).catch(e => erreur(e.message)));
        ajouterMenu(T.diagnostic, () => lancer(instance, 'diagnostic', T.diagnostic).catch(e => erreur(e.message)));
        ajouterMenu(T.dossier, simple(instance, 'dossier'));
        if (!instance.range) {
          ajouterMenu(T.deplacer, () => confirmer(T.deplacer, fmt(T.confirmerDeplacer, {nom: instance.nom}), T.deplacer,
            () => lancer(instance, 'deplacer', T.deplacer)));
        }
      }
    } else if (!instance.connecte) {
      actions.append(bouton(T.connexion, () => seConnecter(instance), 'primary'));
      if (instance.secret_garde) ajouterMenu(T.oublierSecret, simple(instance, 'oublier-secret'));
    } else {
      if (instance.a_console) actions.append(bouton(T.console, simple(instance, 'console'), 'primary'));
      if (etatNom === 'en-marche' || etatNom === 'partielle') {
        actions.append(bouton(T.arreter, () => confirmer(T.arreter, fmt(T.confirmerArreter, {nom: instance.nom}), T.arreter,
          () => lancer(instance, 'arreter', T.arreter))));
      }
      if (etatNom !== 'en-marche') actions.append(bouton(T.demarrer, () => lancer(instance, 'demarrer', T.demarrer).catch(e => erreur(e.message))));
      if (instance.pack) actions.append(bouton(T.pack, () => dialoguePack(instance)));
      ajouterMenu(T.deconnexion, simple(instance, 'deconnexion'));
      if (instance.secret_garde) ajouterMenu(T.oublierSecret, simple(instance, 'oublier-secret'));
    }
    ajouterMenu(T.renommer, () => dialogueRenommer(instance));
    ajouterMenu(T.oublier, () => confirmer(T.oublier, fmt(T.confirmerOublier, {nom: instance.nom}), T.oublier,
      () => api('/api/instances/' + instance.id + '/oublier', {}).then(rafraichir)), 'danger');

    const plus = el('details', {class: 'plus'}, el('summary', {text: T.plus}), menu);
    if (ouverts.has(instance.id)) plus.open = true;
    plus.addEventListener('toggle', () => (plus.open ? ouverts.add(instance.id) : ouverts.delete(instance.id)));
    actions.append(plus);
    if (occupe) for (const b of actions.querySelectorAll('button')) b.disabled = true;

    const enfants = [tete];
    if (mesures.childElementCount) enfants.push(mesures);
    if (etatNom === 'autre-dossier') {
      enfants.push(el('div', {class: 'hors-dossier', text: fmt(T.autreDossier, {chemin: instance.ailleurs || ''})}));
    } else if (instance.type === 'local' && vivante && instance.range === false) {
      enfants.push(el('div', {class: 'hors-dossier', text: T.horsDossier}));
    }
    enfants.push(actions);

    const tache = (etat.taches || []).filter(x => x.instance === instance.id).sort((a, b) => b.debut - a.debut)[0];
    if (tache) {
      enfants.push(el('div', {class: 'tache-ligne'},
        el('span', {class: tache.statut, text: T[tache.action] || tache.action}),
        el('span', {class: 'message', text: T['tache-' + tache.statut] + (tache.message ? ' : ' + tache.message : '')}),
        bouton(T.journal, () => suivreTache(tache.id, (T[tache.action] || tache.action) + ' : ' + instance.nom))));
    }
    return el('section', {class: 'carte', id: 'instance-' + instance.id, 'aria-label': instance.nom}, ...enfants);
  }

  function rendre() {
    $('chargement').hidden = true;
    $('version').textContent = 'PlugArr ' + etat.version;
    $('donnees').textContent = etat.donnees;
    const instances = etat.instances || [];
    $('liste').replaceChildren(...instances.map(carte));
    $('vide').hidden = instances.length > 0;
    $('rail').replaceChildren(...instances.map(i => el('li', {},
      el('a', {href: '#instance-' + i.id},
        el('span', {class: 'point ' + (CLASSES[i.etat] || '')}), el('span', {text: i.nom})))));

    const maj = etat.maj || {};
    $('maj').hidden = maj.etat !== 'disponible';
    if (maj.etat === 'disponible') {
      $('maj-texte').textContent = fmt(T.majDispo, {version: maj.version});
      $('maj-installer').hidden = !maj.installable;
      $('maj-page').hidden = Boolean(maj.installable) || !maj.page;
      if (maj.page) $('maj-page').href = maj.page;
    }
  }

  async function rafraichir() {
    if (ferme) return;
    try {
      const nouveau = await api('/api/etat');
      const empreinte = JSON.stringify(nouveau);
      erreur('');
      if (empreinte === dernier) return;
      dernier = empreinte;
      etat = nouveau;
      rendre();
    } catch (e) {
      erreur(e.message);
    }
  }

  function traduirePage() {
    for (const n of document.querySelectorAll('[data-t]')) {
      const cle = n.getAttribute('data-t');
      if (T[cle]) n.textContent = T[cle];
    }
  }

  async function demarrer() {
    try {
      const reponse = await api('/api/textes');
      T = reponse.textes;
      document.documentElement.lang = reponse.langue;
      if (reponse.icone) {
        $('icone').src = reponse.icone;
        $('icone').hidden = false;
      }
      traduirePage();
    } catch (e) {
      erreur(e.message);
      return;
    }
    if (!jeton) {
      $('chargement').hidden = true;
      erreur(T.erreurSession);
      return;
    }
    $('actualiser').addEventListener('click', async () => {
      await api('/api/actualiser', {}).catch(e => erreur(e.message));
      setTimeout(rafraichir, 1500);
    });
    $('nouvelle').addEventListener('click', async () => {
      erreur('');
      try {
        await api('/api/nouvelle', {});
        info(T.nouvelleLancee);
        setTimeout(() => info(''), 8000);
      } catch (e) {
        erreur(e.message);
      }
    });
    $('quitter').addEventListener('click', async () => {
      await api('/api/quitter', {}).catch(() => {});
      ferme = true;
      clearInterval(rafraichisseur);
      $('liste').replaceChildren();
      info(T.fermeture);
    });
    $('maj-installer').addEventListener('click', () => confirmer(T.majInstaller,
      fmt(T.confirmerMaj, {version: (etat.maj || {}).version}), T.majInstaller, async () => {
        const reponse = await api('/api/maj', {});
        const tache = await suivreTache(reponse.tache.id, T.majInstaller);
        if (tache && tache.statut === 'reussie') {
          ferme = true;
          clearInterval(rafraichisseur);
          info(T.majLancee);
        }
      }));
    await rafraichir();
    rafraichisseur = setInterval(rafraichir, 4000);
  }

  demarrer();
})();
