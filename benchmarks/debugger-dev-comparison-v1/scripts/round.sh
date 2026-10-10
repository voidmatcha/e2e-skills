#!/bin/bash
# round.sh <label> <prev-label-or-base> <mk script>
cd "$(dirname "$0")"; L=$1; PREV=$2; MK=$3
rm -rf plug_$L; cp -R plug_$PREV plug_$L; python3 $MK $PWD/plug_$L || exit 1
./run.sh $L $PWD/plug_$L "skill" 3 && python3 summarize.py $L > $L/summary.txt && python3 judge.py $L > $L/judge.txt
touch $L/ROUND_DONE
