"""The Linux release is a pair of executables, not an unverified tar command."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "linux-bundle.yml").read_text(encoding="utf-8")
DEB = (ROOT / "packaging" / "linux" / "build-deb.sh").read_text(encoding="utf-8")
DESKTOP = (ROOT / "packaging" / "linux" / "plugarr-admin.desktop").read_text(encoding="utf-8")


def test_le_workflow_construit_les_deux_programmes_et_le_runtime_partage():
    assert 'PLUGARR_ONEDIR: "1"' in WORKFLOW
    assert "dist-linux/PlugArr/plugarr" in WORKFLOW
    assert "dist-linux/PlugArr/plugarr-admin" in WORKFLOW
    assert "dist-linux/PlugArr/_internal" in WORKFLOW


def test_la_release_linux_contient_archive_deb_et_somme():
    assert "PlugArr-linux-x86_64.tar.gz" in WORKFLOW
    assert "PlugArr-linux-x86_64.SHA256SUMS" in WORKFLOW
    assert "plugarr_*_amd64.deb" in WORKFLOW
    assert "gh release upload" in WORKFLOW


def test_le_deb_installe_sans_python_et_sans_ecraser_les_donnees():
    assert '"$root/opt/plugarr/"' in DEB
    assert 'ln -s /opt/plugarr/plugarr "$root/usr/bin/plugarr"' in DEB
    assert 'ln -s /opt/plugarr/plugarr-admin "$root/usr/bin/plugarr-admin"' in DEB
    assert "dpkg-deb --root-owner-group --build" in DEB
    assert "postinst" not in DEB and "preinst" not in DEB
    assert "assets/plugarr-mark.svg" in DEB


def test_le_gestionnaire_est_present_dans_le_menu_linux():
    assert "Exec=/opt/plugarr/plugarr-admin" in DESKTOP
    assert "Terminal=false" in DESKTOP
