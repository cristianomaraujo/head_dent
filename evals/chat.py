"""Repeated multi-turn evaluations through /api/chat; cases require expert review."""
import argparse
import csv
import json
from pathlib import Path
import httpx


def run(source, repeats, url, output):
    cases=[json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    for case in cases:
        if not case.get('case_id') or not case.get('reviewed_by') or not case.get('turns'):
            raise ValueError('Each case requires case_id, reviewed_by, context and turns')
        if any(not turn.get('message') or not turn.get('expected_status') for turn in case['turns']):
            raise ValueError('Each turn requires message and expected_status (or no_assessment)')
    with httpx.Client(timeout=110) as client, output.open('w',newline='') as stream, output.with_suffix('.transcripts.jsonl').open('w') as transcripts:
        writer=csv.DictWriter(stream,fieldnames=['case_id','repeat','turn','status','outcome_id','match','error'])
        writer.writeheader()
        for case in cases:
            for repeat in range(1,repeats+1):
                history=[];context=dict(case['context'])
                for number,turn in enumerate(case['turns'],1):
                    row=dict(case_id=case['case_id'],repeat=repeat,turn=number,status='',outcome_id='',match=False,error='')
                    try:
                        response=client.post(url.rstrip('/')+'/api/chat',json=dict(context=context,history=history,message=turn['message']))
                        response.raise_for_status();reply=response.json();assessment=reply.get('assessment') or {}
                        row.update(status=assessment.get('status','no_assessment'),outcome_id=assessment.get('outcome_id'))
                        row['match']=row['status']==turn['expected_status'] and ('expected_outcome_id' not in turn or row['outcome_id']==turn['expected_outcome_id'])
                        history.extend([dict(role='user',content=turn['message']),dict(role='assistant',content=json.dumps(reply,ensure_ascii=False))])
                        context['guideline']=reply['guideline']
                        transcripts.write(json.dumps(dict(case_id=case['case_id'],repeat=repeat,turn=number,message=turn['message'],reply=reply),ensure_ascii=False)+'\n')
                    except (httpx.HTTPError,KeyError,ValueError) as error:
                        row['error']=str(error)
                    writer.writerow(row);stream.flush();transcripts.flush()
                    if row['error']: break


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('cases',type=Path);parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--url',default='http://127.0.0.1:8000');parser.add_argument('--output',type=Path,default=Path('chat-results.csv'))
    args=parser.parse_args()
    if args.repeats<1: parser.error('--repeats must be positive')
    run(args.cases,args.repeats,args.url,args.output)
