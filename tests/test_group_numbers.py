from app.pipeline import group_documents

def doc(i,side,number,source=None):
    return {'id':str(i),'source_id':str(i) if source is None else source,'kind':'national_id','side':side,'fields':[{'key':'document_number','value':number,'pairing_eligible':True,'serial_location':'below_portrait' if side=='front' else 'mrz_first_line','mrz_checksum':True}]}

def test_matching_number_pairs_across_sources():
    ds=[doc(1,'front','AB1234567'),doc(2,'back','AB1234567')]
    group_documents(ds)
    assert ds[0]['group']==ds[1]['group']

def test_different_numbers_stay_separate():
    ds=[doc(1,'front','AB1234567'),doc(2,'back','AB1234568')]
    group_documents(ds)
    assert ds[0]['group']!=ds[1]['group']

def test_conflicting_numbers_on_same_page_stay_separate():
    ds=[doc(1,'front','AB1234567','s'),doc(2,'back','AB1234568','s')]
    group_documents(ds)
    assert ds[0]['group']!=ds[1]['group']

def test_duplicate_candidates_require_review():
    ds=[doc(1,'front','AB1234567'),doc(2,'back','AB1234567'),doc(3,'back','AB1234567')]
    group_documents(ds)
    assert len({d['group'] for d in ds})==3

def test_number_pair_has_priority_and_leaves_unmatched_side_separate():
    ds=[doc(1,'front','AB1234567','s'),doc(2,'back','','s'),doc(3,'back','AB1234567')]
    group_documents(ds)
    assert ds[0]['group']==ds[2]['group']
    assert ds[1]['group']!=ds[0]['group']
