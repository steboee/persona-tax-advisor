from taxadvisor.laws.htmltext import html_to_text


def test_headings_blocks_and_skipped_tags():
    html = """
    <html><head><title>x</title><style>.a{}</style></head><body>
    <nav>Menu Domov</nav>
    <div class="predpis">
      <div>PRVÁ ČASŤ</div><div>VŠEOBECNÉ USTANOVENIA</div>
      <div class="paragraf"><span>§&nbsp;21</span></div>
      <div>Výdavky, ktoré nie sú daňovými výdavkami</div>
      <p>(1) Daňovými výdavkami nie sú<br>h) výdavky na reprezentáciu,</p>
      <table><tr><td>do 50 000 eur</td><td>340 eur</td></tr></table>
      <script>alert("no")</script>
    </div></body></html>
    """
    text = html_to_text(html)
    lines = text.splitlines()
    assert "## PRVÁ ČASŤ" in lines
    assert "### § 21" in lines
    assert "(1) Daňovými výdavkami nie sú" in lines
    assert "h) výdavky na reprezentáciu," in lines
    assert "do 50 000 eur | 340 eur" in lines
    assert "alert" not in text and "Menu Domov" not in text and ".a{}" not in text
