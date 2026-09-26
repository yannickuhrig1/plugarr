; Installateur Windows de PlugArr (Inno Setup 6).
;
;     set PLUGARR_ONEDIR=1
;     pyinstaller packaging/plugarr.spec --noconfirm
;     ISCC packaging/installer/plugarr.iss /DVersion=0.11.0
;
; Ce qu'il pose, et pourquoi a cet endroit :
;
; - les PROGRAMMES dans %LOCALAPPDATA%\Programs\PlugArr : installation par
;   utilisateur, sans demande de droits administrateur. La mise a jour doit
;   pouvoir reecrire ce dossier sans UAC, et le demarrage automatique de la
;   console est lui aussi par session ;
; - rien d'autre. Les DONNEES (installations, secrets, journaux) vivent dans
;   %LOCALAPPDATA%\plugarr, que PlugArr cree lui-meme. La desinstallation n'y
;   touche JAMAIS : `stack.yml` est la seule copie en clair des mots de passe
;   que Jellyfin ou qBittorrent ne gardent que haches.
;
; Mise a jour silencieuse, lancee par le gestionnaire (selfupdate.py) :
;
;     PlugArr-Setup-x.y.z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
;         /CLOSEAPPLICATIONS /SP- /RELANCER=1

#ifndef Version
  #error Passez la version : ISCC /DVersion=x.y.z
#endif
#ifndef Source
  #define Source "..\..\dist\PlugArr"
#endif
#ifndef Sortie
  #define Sortie "..\..\dist"
#endif

[Setup]
; Ne JAMAIS changer cet identifiant : c'est lui qui fait qu'une nouvelle
; version remplace l'ancienne au lieu de s'installer a cote.
AppId={{8C5B2E57-3E1F-4B8A-9D3A-6F1B2C7A9E41}
AppName=PlugArr
AppVersion={#Version}
AppVerName=PlugArr {#Version}
AppPublisher=PlugArr
AppPublisherURL=https://github.com/yannickuhrig1/plugarr
AppSupportURL=https://github.com/yannickuhrig1/plugarr/issues
AppUpdatesURL=https://github.com/yannickuhrig1/plugarr/releases
; Avec PrivilegesRequired=lowest, {autopf} vaut %LOCALAPPDATA%\Programs.
DefaultDirName={autopf}\PlugArr
DefaultGroupName=PlugArr
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir={#Sortie}
OutputBaseFilename=PlugArr-Setup-{#Version}
SetupIconFile=..\..\assets\plugarr.ico
UninstallDisplayIcon={app}\plugarr-admin.exe
UninstallDisplayName=PlugArr
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Le gestionnaire est ferme proprement dans PrepareToInstall ; le Restart
; Manager ne sert qu'en dernier recours.
CloseApplications=yes
RestartApplications=no
; La tache « PATH » modifie l'environnement de l'utilisateur.
ChangesEnvironment=yes
VersionInfoVersion={#Version}
VersionInfoProductName=PlugArr

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.TacheBureau=Créer un raccourci PlugArr sur le bureau
en.TacheBureau=Create a PlugArr desktop shortcut
fr.TachePath=Ajouter plugarr au PATH, pour la ligne de commande
en.TachePath=Add plugarr to the PATH, for the command line
fr.RaccourciAssistant=Assistant PlugArr
en.RaccourciAssistant=PlugArr wizard
fr.OuvrirApres=Ouvrir PlugArr
en.OuvrirApres=Open PlugArr
fr.DonneesConservees=PlugArr est désinstallé.%n%nVos installations et leurs réglages sont conservés dans :%n%1%n%nLes services Docker déjà installés continuent de tourner. Pour les arrêter, utilisez « plugarr uninstall » avant de désinstaller, ou arrêtez-les depuis Docker Desktop.
en.DonneesConservees=PlugArr is uninstalled.%n%nYour installations and their settings are kept in:%n%1%n%nDocker services already installed keep running. To stop them, use "plugarr uninstall" before uninstalling, or stop them from Docker Desktop.

[Tasks]
Name: "bureau"; Description: "{cm:TacheBureau}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "path"; Description: "{cm:TachePath}"; Flags: unchecked

[InstallDelete]
; Le runtime d'une version precedente : des bibliotheques renommees d'une
; version a l'autre resteraient sinon a cote des nouvelles.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PlugArr"; Filename: "{app}\plugarr-admin.exe"
Name: "{autoprograms}\{cm:RaccourciAssistant}"; Filename: "{app}\plugarr.exe"; Parameters: "web"
Name: "{autodesktop}\PlugArr"; Filename: "{app}\plugarr-admin.exe"; Tasks: bureau

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: path; Check: CheminAbsent(ExpandConstant('{app}'))

[Run]
Filename: "{app}\plugarr-admin.exe"; Description: "{cm:OuvrirApres}"; Flags: nowait postinstall skipifsilent
; Mise a jour lancee depuis le gestionnaire : il s'est ferme pour laisser
; remplacer ses fichiers, on le rouvre.
Filename: "{app}\plugarr-admin.exe"; Flags: nowait; Check: DoitRelancer

[Code]
function DoitRelancer: Boolean;
begin
  Result := ExpandConstant('{param:RELANCER|0}') = '1';
end;

function CheminAbsent(const Dossier: String): Boolean;
var
  Actuel: String;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Actuel) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dossier) + ';', ';' + Uppercase(Actuel) + ';') = 0;
end;

procedure RetirerDuChemin(const Dossier: String);
var
  Ancien, Reste, Morceau, Nouveau: String;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Ancien) then
    exit;
  Reste := Ancien;
  Nouveau := '';
  while Reste <> '' do
  begin
    P := Pos(';', Reste);
    if P = 0 then
    begin
      Morceau := Reste;
      Reste := '';
    end
    else
    begin
      Morceau := Copy(Reste, 1, P - 1);
      Delete(Reste, 1, P);
    end;
    if (Morceau <> '') and (CompareText(Morceau, Dossier) <> 0) then
    begin
      if Nouveau <> '' then
        Nouveau := Nouveau + ';';
      Nouveau := Nouveau + Morceau;
    end;
  end;
  if Nouveau <> Ancien then
    RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Nouveau);
end;

{ Demande au gestionnaire ouvert de se fermer, par la commande qu'il connait.
  Sans cela, ses fichiers seraient verrouilles pendant la copie. }
procedure FermerGestionnaire;
var
  Moteur: String;
  Code: Integer;
begin
  Moteur := ExpandConstant('{app}\plugarr.exe');
  if FileExists(Moteur) then
    Exec(Moteur, 'manager --quitter', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  FermerGestionnaire;
  Result := '';
end;

{ Le demarrage automatique de la console (`plugarr autostart`) ecrit un
  lanceur dans le dossier Demarrage. S'il pointe vers les programmes qu'on
  retire, il echouerait a chaque ouverture de session. }
procedure RetirerDemarrageAuto;
var
  Lanceur: String;
  Contenu: AnsiString;
begin
  Lanceur := ExpandConstant('{userstartup}\plugarr-console.cmd');
  if not FileExists(Lanceur) then
    exit;
  if not LoadStringFromFile(Lanceur, Contenu) then
    exit;
  if Pos(Lowercase(ExpandConstant('{app}')), Lowercase(String(Contenu))) > 0 then
    DeleteFile(Lanceur);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    FermerGestionnaire;
    RetirerDemarrageAuto;
    RetirerDuChemin(ExpandConstant('{app}'));
  end;
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
    MsgBox(FmtMessage(CustomMessage('DonneesConservees'), [ExpandConstant('{localappdata}\plugarr')]),
      mbInformation, MB_OK);
end;
