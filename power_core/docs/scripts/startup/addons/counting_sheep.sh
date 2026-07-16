#!/bin/bash
#dependency: timer.sh
wait_and_counting_sheep() {
      timer_pause # function form timer.sh
      local total_time=$1 # int 10,20,30 etc...
      echo "⏱ Waiting ${total_time} seconds to make sure the cloud has processed the request...."
      for i in $(seq "$total_time" -1 1); do
          # Use \r to return to the start of the line and overwrite the previous text
          printf "   Estimated time remaining: %2d seconds...\r" "$i"
          sleep 1
      done

      printf "\r%40s\r" "" # Clear the final countdown line
      echo "🮱 Continue installing..."
      timer_start # function form timer.sh
}