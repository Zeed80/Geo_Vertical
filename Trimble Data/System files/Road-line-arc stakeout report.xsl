<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt" >

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="html" omit-xml-declaration="no"  encoding="utf-8"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="DegreesSymbol" select="'&#0176;'"/>
<xsl:variable name="MinutesSymbol"><xsl:text>'</xsl:text></xsl:variable>
<xsl:variable name="SecondsSymbol" select="'&quot;'"/>

<xsl:variable name="fileExt" select="'htm'"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->

<xsl:variable name="userField1" select="'StnSOTol|Station tolerance|double|0.0|1.0'"/>
<xsl:variable name="StnSOTol" select="0.05"/>
<xsl:variable name="userField2" select="'OffsSOTol|Offset tolerance|double|0.0|1.0'"/>
<xsl:variable name="OffsSOTol" select="0.02"/>
<xsl:variable name="userField3" select="'VtSOTol|Vertical tolerance|double|0.0|1.0'"/>
<xsl:variable name="VtSOTol" select="0.05"/>
<xsl:variable name="userField4" select="'PtIdentification|Point identification|stringMenu|2|Station/Offset|Point name'"/>
<xsl:variable name="PtIdentification" select="'Station/Offset'"/>
<xsl:variable name="userField5" select="'useDTMDeltas|Report deltaelevations to DTM|stringMenu|2|Yes|No'"/>
<xsl:variable name="useDTMDeltas" select="'Yes'"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="product">
  <xsl:choose>
    <xsl:when test="JOBFile/@product"><xsl:value-of select="JOBFile/@product"/></xsl:when>
    <xsl:otherwise>Trimble Survey Controller</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="version">
  <xsl:choose>
    <xsl:when test="JOBFile/@productVersion"><xsl:value-of select="JOBFile/@productVersion"/></xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number(JOBFile/@version div 100, $DecPl2, 'Standard')"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="FormatStyle" select="/JOBFile/Environment/DisplaySettings/StationingFormat"/>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <HTML>

  <Title>Stakeout Report</Title>
  <h2>Stakeout Report</h2>

  <HEAD>
  </HEAD>

  <BODY>
  <TABLE BORDER="0" width="100%" cellpadding="5">
    <TR>
      <TD>Job name:</TD>
      <TD><xsl:value-of select="JOBFile/@jobName"/></TD>
    </TR>
    <TR>
      <TD><xsl:value-of select="$product"/> version:</TD>
      <TD><xsl:value-of select="$version"/></TD>
    </TR>
    <xsl:if test="JOBFile/@TimeStamp != ''"> <!-- Date could be null in an updated job -->
      <TR>
        <TD>Creation date:</TD>
        <TD><xsl:value-of select="substring-before(JOBFile/@TimeStamp, 'T')"/></TD>
      </TR>
    </xsl:if>
    <TR>
      <TD>Distance/Coord units:</TD>
      <TD><xsl:value-of select="$DistUnit"/></TD>
    </TR>
    <TR>
      <TD>Angle units:</TD>
      <TD><xsl:value-of select="$AngleUnit"/></TD>
    </TR>
    <TR>
      <TD>Stakeout station tolerance:</TD>
      <TD><xsl:value-of select="format-number(number($StnSOTol), $DecPl3, 'Standard')"/></TD>
    </TR>
    <TR>
      <TD>Stakeout offset tolerance:</TD>
      <TD><xsl:value-of select="format-number(number($OffsSOTol), $DecPl3, 'Standard')"/></TD>
    </TR>
    <TR>
      <TD>Stakeout vertical tolerance:</TD>
      <TD><xsl:value-of select="format-number(number($VtSOTol), $DecPl3, 'Standard')"/></TD>
    </TR>
  </TABLE>  
  
  <xsl:call-template name="SeparatingLine"/>
  <BR/>
  <TABLE border="1" width="100%" cellpadding="2">
    <CAPTION><xsl:value-of select="'Highlighted values exceed stakeout tolerances.'"/></CAPTION>
    <THEAD>
      <TR>
        <xsl:choose>
          <xsl:when test="$useDTMDeltas != 'Yes'">
            <xsl:choose>
              <xsl:when test="$PtIdentification = 'Station/Offset'">
                <TD width="37%" align="center"><SMALL><B>Station/Offset</B></SMALL></TD>
              </xsl:when>
              <xsl:otherwise>
                <TD width="37%" align="center"><SMALL><B>Name</B></SMALL></TD>
              </xsl:otherwise>
            </xsl:choose>
            <TD width="15%" align="center"><SMALL><B>dStation</B></SMALL></TD>
            <TD width="15%" align="center"><SMALL><B>dOffset</B></SMALL></TD>
            <TD width="15%" align="center"><SMALL><B>dElev</B></SMALL></TD>
            <TD width="18%" align="center"><SMALL><B>Code</B></SMALL></TD>
          </xsl:when>
          <xsl:otherwise>
            <xsl:choose>
              <xsl:when test="$PtIdentification = 'Station/Offset'">
                <TD width="19%" align="center"><SMALL><B>Station/Offset</B></SMALL></TD>
              </xsl:when>
              <xsl:otherwise>
                <TD width="19%" align="center"><SMALL><B>Name</B></SMALL></TD>
              </xsl:otherwise>
            </xsl:choose>
            <TD width="15%" align="center"><SMALL><B>dStation</B></SMALL></TD>
            <TD width="15%" align="center"><SMALL><B>dOffset</B></SMALL></TD>
            <TD width="15%" align="center"><SMALL><B>dElev</B></SMALL></TD>
            <TD width="18%" align="center"><SMALL><B>DTM</B></SMALL></TD>
            <TD width="18%" align="center"><SMALL><B>Code</B></SMALL></TD>
          </xsl:otherwise>
        </xsl:choose>
      </TR>
    </THEAD>
    <TBODY>

    <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />

    </TBODY>
  </TABLE>
  </BODY>
  </HTML>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">

  <xsl:variable name="stakedPoints">
    <xsl:for-each select="PointRecord[(Stakeout/RoadDesign) or (Stakeout/LineDesign) or (Stakeout/ArcDesign)]">
      <xsl:copy>
        <xsl:copy-of select="* | @*"/>
      </xsl:copy>
    </xsl:for-each>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$PtIdentification = 'Station/Offset'">
      <xsl:for-each select="msxsl:node-set($stakedPoints)/*">
        <xsl:sort data-type="number" select="Stakeout/RoadDesign/Station"/>
        <xsl:sort data-type="number" select="Stakeout/RoadDesign/Offset"/>
        <xsl:call-template name="StakeoutDeltas"/>
      </xsl:for-each>
    </xsl:when>
    <xsl:otherwise>
      <xsl:for-each select="msxsl:node-set($stakedPoints)/*">
        <xsl:call-template name="StakeoutDeltas"/>
      </xsl:for-each>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Stakeout Deltas Details Output ****************** -->
<!-- **************************************************************** -->
<xsl:template name="StakeoutDeltas">
  <xsl:variable name="dStnStr" select="format-number(Stakeout/LinearDeltas/DeltaStation * $DistConvFactor, $DecPl3, 'Standard')"/>

  <xsl:variable name="dOffsStr" select="format-number(Stakeout/LinearDeltas/DeltaOffset * $DistConvFactor, $DecPl3, 'Standard')"/>

  <xsl:variable name="dElev">
    <xsl:choose>
      <xsl:when test="(string(number(Stakeout/GridDeltas/DeltaElevation)) != 'NaN') and ($useDTMDeltas != 'Yes')">
        <xsl:value-of select="Stakeout/GridDeltas/DeltaElevation"/>
      </xsl:when>
      <xsl:when test="(string(number(Stakeout/LinearDeltas/DeltaElevation)) != 'NaN') and ($useDTMDeltas != 'Yes')">
        <xsl:value-of select="Stakeout/LinearDeltas/DeltaElevation"/>
      </xsl:when>
      <xsl:when test="$useDTMDeltas = 'Yes'">
        <xsl:value-of select="Stakeout/DeltasRelativeToDTM/DeltaElevation"/>
      </xsl:when>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="dElevStr">
    <xsl:value-of select="format-number($dElev * $DistConvFactor, $DecPl3, 'Standard')"/>
  </xsl:variable>

  <xsl:variable name="StnValue">
    <xsl:if test="Stakeout/RoadDesign">
      <xsl:choose>
        <xsl:when test="Stakeout/RoadDesign/EquatedStation">
          <xsl:value-of select="Stakeout/RoadDesign/EquatedStation/Station"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="Stakeout/RoadDesign/Station"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:if>
    <xsl:if test="Stakeout/LineDesign">
      <xsl:value-of select="Stakeout/LineDesign/Station"/>
    </xsl:if>
    <xsl:if test="Stakeout/ArcDesign">
      <xsl:value-of select="Stakeout/ArcDesign/Station"/>
    </xsl:if>
  </xsl:variable>
  
  <xsl:variable name="StnZone">
    <xsl:if test="Stakeout/RoadDesign">
      <xsl:choose>
        <xsl:when test="Stakeout/RoadDesign/EquatedStation">
          <xsl:value-of select="Stakeout/RoadDesign/EquatedStation/Zone"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="''"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:if>
    <xsl:if test="Stakeout/LineDesign">
      <xsl:value-of select="''"/>
    </xsl:if>
    <xsl:if test="Stakeout/ArcDesign">
      <xsl:value-of select="''"/>
    </xsl:if>
  </xsl:variable>
  
  <xsl:variable name="OffsetVal">
    <xsl:if test="Stakeout/RoadDesign">
      <xsl:choose>
        <xsl:when test="Stakeout/RoadDesign/Offset != ''">
          <xsl:value-of select="format-number(Stakeout/RoadDesign/Offset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:when test="Stakeout/CatchPoint/Offset and 
                        (Stakeout/CatchPoint/Offset &gt; 0.0)">
          <xsl:value-of select="'R Catch'"/>
        </xsl:when>
        <xsl:when test="Stakeout/CatchPoint/Offset and 
                        (Stakeout/CatchPoint/Offset &lt; 0.0)">
          <xsl:value-of select="'L Catch'"/>
        </xsl:when>
      </xsl:choose>
    </xsl:if>

    <xsl:if test="Stakeout/LineDesign">
      <xsl:value-of select="format-number(Stakeout/LineDesign/Offset * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:if>

    <xsl:if test="Stakeout/ArcDesign">
      <xsl:value-of select="format-number(Stakeout/ArcDesign/Offset * $DistConvFactor, $DecPl3, 'Standard')"/>
    </xsl:if>
  </xsl:variable>
  
  <xsl:variable name="PtIDStr">
    <xsl:choose>
      <xsl:when test="$PtIdentification = 'Station/Offset'">
        <xsl:variable name="StnVal">
          <xsl:call-template name="FormattedStationVal">
            <xsl:with-param name="StationVal" select="$StnValue"/>
            <xsl:with-param name="ZoneVal" select="$StnZone"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:value-of select="concat($StnVal, '/', $OffsetVal)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="Name"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Create absolute value delta elevation equivalent for tolerance testing purposes -->
  <xsl:variable name="dAbsStn" select="concat(substring('-',2 - ((Stakeout/LinearDeltas/DeltaStation * $DistConvFactor) &lt; 0)), '1') * (Stakeout/LinearDeltas/DeltaStation * $DistConvFactor)"/>

  <xsl:variable name="dAbsOffs" select="concat(substring('-',2 - ((Stakeout/LinearDeltas/DeltaOffset * $DistConvFactor) &lt; 0)), '1') * (Stakeout/LinearDeltas/DeltaOffset * $DistConvFactor)"/>

  <xsl:variable name="dAbsElev" select="concat(substring('-',2 - (($dElev * $DistConvFactor) &lt; 0)), '1') * ($dElev * $DistConvFactor)"/>

  <TR>
    <xsl:choose>
      <xsl:when test="$useDTMDeltas != 'Yes'">
        <TD width="37%" align="left"><SMALL><xsl:value-of select="$PtIDStr"/></SMALL></TD>
      </xsl:when>
      <xsl:otherwise>
        <TD width="19%" align="left"><SMALL><xsl:value-of select="$PtIDStr"/></SMALL></TD>
      </xsl:otherwise>
    </xsl:choose>

    <xsl:choose>
      <xsl:when test="$dAbsStn > $StnSOTol">
        <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dStnStr"/></SMALL></B></FONT></TD>
      </xsl:when>
      <xsl:otherwise>
        <TD width="15%" align="right"><SMALL><xsl:value-of select="$dStnStr"/></SMALL></TD>
      </xsl:otherwise>
    </xsl:choose>

    <xsl:choose>
      <xsl:when test="$dAbsOffs > $OffsSOTol">
        <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dOffsStr"/></SMALL></B></FONT></TD>
      </xsl:when>
      <xsl:otherwise>
        <TD width="15%" align="right"><SMALL><xsl:value-of select="$dOffsStr"/></SMALL></TD>
      </xsl:otherwise>
    </xsl:choose>

    <xsl:choose>
      <xsl:when test="$dAbsElev > $VtSOTol">
        <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dElevStr"/></SMALL></B></FONT></TD>
      </xsl:when>
      <xsl:otherwise>
        <TD width="15%" align="right"><SMALL><xsl:value-of select="$dElevStr"/></SMALL></TD>
      </xsl:otherwise>
    </xsl:choose>
    
    <xsl:if test="$useDTMDeltas = 'Yes'">
      <TD width="18%" align="left"><SMALL><xsl:value-of select="Stakeout/DeltasRelativeToDTM/DTMName"/></SMALL></TD>
    </xsl:if>

    <TD width="18%" align="left"><SMALL><xsl:value-of select="Code"/></SMALL></TD>
  </TR>

</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return Formatted Station Value ***************** -->
<!-- **************************************************************** -->
<xsl:template name="FormattedStationVal">
  <xsl:param name="StationVal"/>
  <xsl:param name="ZoneVal" select="''"/>

  <xsl:variable name="StnVal" select="format-number($StationVal * $DistConvFactor, $DecPl3, 'Standard')"/>
  <xsl:variable name="SignChar">
    <xsl:choose>
      <xsl:when test="$StnVal &lt; 0.0">
        <xsl:value-of select="'-'"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="''"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="AbsStnVal" select="concat(substring('-',2 - ($StnVal &lt; 0)), '1') * $StnVal"/>

  <xsl:variable name="IntPart" select="substring-before(format-number($AbsStnVal, $DecPl3, 'Standard'), '.')"/>
  <xsl:variable name="DecPart" select="substring-after($StnVal, '.')"/>
  
  <xsl:if test="$FormatStyle = '1000.0'">
    <xsl:value-of select="$StnVal"/>
  </xsl:if>
 
  <xsl:if test="$FormatStyle = '10+00.0'">
    <xsl:choose>
      <xsl:when test="string-length($IntPart) > 2">
        <xsl:value-of select="concat($SignChar, substring($IntPart, 1, string-length($IntPart) - 2),
                                     '+', substring($IntPart, string-length($IntPart) - 1, 2), 
                                     '.', $DecPart)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="concat($SignChar, '0+', substring('00', 1, 2 - string-length($IntPart)), 
                                     $IntPart, '.', $DecPart)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>

  <xsl:if test="$FormatStyle = '1+000.0'">
    <xsl:choose>
      <xsl:when test="string-length($IntPart) > 3">
        <xsl:value-of select="concat($SignChar, substring($IntPart, 1, string-length($IntPart) - 3),
                                     '+', substring($IntPart, string-length($IntPart) - 2, 3), 
                                     '.', $DecPart)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="concat($SignChar, '0+', substring('000', 1, 3 - string-length($IntPart)), 
                                     $IntPart, '.', $DecPart)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>

  <xsl:if test="$ZoneVal != ''">
    <xsl:value-of select="':'"/>
    <xsl:value-of select="format-number($ZoneVal,'0')"/>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


</xsl:stylesheet>